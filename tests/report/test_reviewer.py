"""Unit tests for the reviewer: deterministic pre-check + LLM judge, fail-closed."""

from __future__ import annotations

from genome_firewall.llm.mock import MockLLMClient
from genome_firewall.report.builder import build_report
from genome_firewall.report.inputs import GenomePredictionInputs
from genome_firewall.report.narrative import render_row
from genome_firewall.report.nl_schemas import (
    NLDrugNarrative,
    NLReportSection,
    ReportVerdict,
)
from genome_firewall.report.reviewer import _PERCENT_RE, deterministic_precheck, review_narrative
from tests.report.conftest import (
    make_prediction_inputs,
    meropenem_gate_input,
)

_REPORT = build_report(make_prediction_inputs("g1"))
_NO_RETRIEVAL: dict = {}


def _section(*drugs: NLDrugNarrative, summary: str = "Summary.") -> NLReportSection:
    return NLReportSection(summary=summary, per_antibiotic=drugs)


def test_precheck_passes_a_grounded_narrative() -> None:
    section = _section(
        NLDrugNarrative(antibiotic="meropenem", narrative="Meropenem is LIKELY TO FAIL."),
        NLDrugNarrative(antibiotic="ceftriaxone", narrative="Ceftriaxone is LIKELY TO WORK."),
    )
    ok, _ = deterministic_precheck(section, _REPORT, _NO_RETRIEVAL)
    assert ok


def test_precheck_rejects_a_fabricated_number() -> None:
    # A non-percentage number absent from the report and citations (general number path).
    section = _section(summary="Meropenem was supported by 4242 sequencing reads.")
    ok, reason = deterministic_precheck(section, _REPORT, _NO_RETRIEVAL)
    assert not ok
    assert "number" in reason


def test_precheck_rejects_a_fabricated_drug() -> None:
    # A per-antibiotic entry for a drug not evaluated in this report must be rejected.
    section = _section(
        NLDrugNarrative(antibiotic="colistin", narrative="Colistin is likely to work.")
    )
    ok, reason = deterministic_precheck(section, _REPORT, _NO_RETRIEVAL)
    assert not ok
    assert "colistin" in reason


def test_precheck_rejects_a_fabricated_verdict_word() -> None:
    # A report where nothing is LIKELY TO WORK; claiming it is fabricates a verdict.
    fail_report = build_report(
        GenomePredictionInputs(genome_id="g1", drugs=(meropenem_gate_input(),))
    )
    section = _section(
        NLDrugNarrative(antibiotic="meropenem", narrative="Meropenem is LIKELY TO WORK.")
    )
    ok, reason = deterministic_precheck(section, fail_report, _NO_RETRIEVAL)
    assert not ok
    assert "verdict" in reason


def test_precheck_rejects_causal_language_on_a_statistical_row() -> None:
    # A ceftriaxone model row driven by a statistical feature (no known mechanism).
    stat_report = build_report(
        GenomePredictionInputs(
            genome_id="g1",
            drugs=(_ceftriaxone_statistical_input(),),
        )
    )
    section = _section(
        NLDrugNarrative(
            antibiotic="ceftriaxone",
            narrative="Ceftriaxone LIKELY TO FAIL; the detected gene confers resistance.",
        )
    )
    ok, reason = deterministic_precheck(section, stat_report, _NO_RETRIEVAL)
    assert not ok
    assert "causal" in reason


def _ceftriaxone_statistical_input():
    from genome_firewall.report.inputs import DrugPredictionInput
    from genome_firewall.schemas import ConformalSet, ModelPrediction
    from tests.report.conftest import vector

    return DrugPredictionInput(
        antibiotic="ceftriaxone",
        vector=vector(),  # no cephalosporinase gene -> not a known mechanism
        model_prediction=ModelPrediction(probability_resistant=0.7, model_version="lr-v1"),
        conformal_set=ConformalSet(labels=("R",), alpha=0.1),
        model_top_features=("eng:has_esbl_or_ampc",),
    )


def test_precheck_is_a_fixed_phrase_guard_not_a_semantic_verifier() -> None:
    # DOCUMENTS the boundary (ADR-0020): a wrong verdict expressed with a non-canonical synonym
    # ("should remain effective" for a likely_to_fail drug) is NOT caught by the deterministic
    # pre-check -- that is the LLM judge's job (defense-in-depth). Pinned so it isn't mistaken
    # for a bug: the pre-check catches the crudest fixed-phrase failures, not paraphrase.
    section = _section(
        NLDrugNarrative(antibiotic="meropenem", narrative="Meropenem should remain effective.")
    )
    ok, _ = deterministic_precheck(section, _REPORT, _NO_RETRIEVAL)
    assert ok  # passes the pre-check; the judge must catch the semantic contradiction


def test_precheck_uses_word_boundaries_so_no_callback_is_not_a_no_call() -> None:
    section = NLReportSection(
        summary="No callback from the lab is expected.", per_antibiotic=(), caveats=()
    )
    ok, _ = deterministic_precheck(section, _REPORT, _NO_RETRIEVAL)
    assert ok  # 'no callback' must not trip the 'no call' verdict phrase


def test_review_short_circuits_before_the_llm_when_precheck_fails() -> None:
    section = _section(summary="Meropenem resistance is 42% likely.")
    # An empty mock would raise on any call; the pre-check must reject first.
    outcome = review_narrative(section, _REPORT, _NO_RETRIEVAL, MockLLMClient({}))
    assert not outcome.passed
    assert "pre-check" in outcome.reason


def test_review_passes_when_precheck_and_judge_pass() -> None:
    section = _section(
        NLDrugNarrative(antibiotic="meropenem", narrative="Meropenem is LIKELY TO FAIL.")
    )
    client = MockLLMClient({"report_review": ReportVerdict(grounding_score=1.0, overall_pass=True)})
    outcome = review_narrative(section, _REPORT, _NO_RETRIEVAL, client)
    assert outcome.passed
    assert outcome.verdict is not None


def test_review_fails_closed_when_judge_rejects() -> None:
    section = _section(
        NLDrugNarrative(antibiotic="meropenem", narrative="Meropenem is LIKELY TO FAIL.")
    )
    client = MockLLMClient(
        {"report_review": ReportVerdict(grounding_score=0.2, overall_pass=False)}
    )
    outcome = review_narrative(section, _REPORT, _NO_RETRIEVAL, client)
    assert not outcome.passed


def test_review_fails_closed_on_llm_error() -> None:
    section = _section(
        NLDrugNarrative(antibiotic="meropenem", narrative="Meropenem is LIKELY TO FAIL.")
    )
    # No scripted "report_review" -> MockLLMClient raises LLMRefusalError -> fail closed.
    outcome = review_narrative(section, _REPORT, _NO_RETRIEVAL, MockLLMClient({"other": "{}"}))
    assert not outcome.passed
    assert "error" in outcome.reason


def test_precheck_rejects_a_per_drug_verdict_swap_in_a_mixed_report() -> None:
    # _REPORT has meropenem=likely_to_fail AND ceftriaxone=likely_to_work, so BOTH verdict
    # phrases exist somewhere in the report -- a global membership check would miss this swap.
    section = _section(
        NLDrugNarrative(antibiotic="meropenem", narrative="Meropenem is LIKELY TO WORK."),
    )
    ok, reason = deterministic_precheck(section, _REPORT, _NO_RETRIEVAL)
    assert not ok
    assert "meropenem" in reason and "likely to work" in reason


def test_precheck_rejects_any_verdict_phrase_in_the_summary() -> None:
    # The free-text summary may not state a per-drug verdict at all (they belong in per_antibiotic).
    section = _section(summary="For meropenem, the drug is likely to work.")
    ok, reason = deterministic_precheck(section, _REPORT, _NO_RETRIEVAL)
    assert not ok
    assert "summary" in reason and "likely to work" in reason


def test_precheck_rejects_a_verdict_phrase_in_a_caveat() -> None:
    section = NLReportSection(
        summary="Summary.",
        per_antibiotic=(),
        caveats=("Note that meropenem is likely to work here.",),
    )
    ok, reason = deterministic_precheck(section, _REPORT, _NO_RETRIEVAL)
    assert not ok
    assert "caveat" in reason and "likely to work" in reason


def test_precheck_rejects_a_plural_verdict_statement_in_the_summary() -> None:
    # A plural/aggregate sentence covering several drugs must not slip a wrong verdict through
    # (the proximity-attribution hole the outright ban closes).
    section = _section(summary="Meropenem and ceftriaxone are both likely to work.")
    ok, reason = deterministic_precheck(section, _REPORT, _NO_RETRIEVAL)
    assert not ok
    assert "likely to work" in reason


def test_precheck_rejects_a_foreign_drug_named_in_a_per_antibiotic_narrative() -> None:
    # Same masking class as the summary plural case, relocated inside a per-drug entry: meropenem's
    # narrative naming ceftriaxone and asserting an aggregate verdict must be rejected outright.
    section = _section(
        NLDrugNarrative(
            antibiotic="meropenem",
            narrative="Meropenem and ceftriaxone are both likely to fail.",
        )
    )
    ok, reason = deterministic_precheck(section, _REPORT, _NO_RETRIEVAL)
    assert not ok
    assert "meropenem" in reason and "ceftriaxone" in reason


def test_precheck_rejects_a_foreign_causal_claim_inside_a_known_mechanism_entry() -> None:
    # A causal claim about a different (statistical) drug hidden in a known-mechanism entry.
    section = _section(
        NLDrugNarrative(
            antibiotic="meropenem",
            narrative="For ceftriaxone the detected gene confers resistance.",
        )
    )
    ok, reason = deterministic_precheck(section, _REPORT, _NO_RETRIEVAL)
    assert not ok
    assert "ceftriaxone" in reason


def test_precheck_rejects_causal_language_in_the_summary() -> None:
    section = _section(summary="For ceftriaxone, the detected gene confers resistance.")
    ok, reason = deterministic_precheck(section, _REPORT, _NO_RETRIEVAL)
    assert not ok
    assert "summary" in reason and "causal" in reason


def test_precheck_rejects_a_fabricated_confidence_even_if_the_digits_appear_in_kb_text() -> None:
    from genome_firewall.kb.corpus import KBChunk
    from genome_firewall.kb.retriever import RetrievedChunk

    # A KB chunk mentioning "95% identity" must not license a fabricated 95% confidence.
    retrieval = {
        "meropenem": (
            RetrievedChunk(
                chunk=KBChunk(
                    chunk_id="c", gene_family="g", text="95% identity to reference", source="s"
                ),
                score=1.0,
            ),
        )
    }
    section = _section(summary="Meropenem resistance is 95% likely.")
    ok, reason = deterministic_precheck(section, _REPORT, retrieval)
    assert not ok
    assert "confidence" in reason


def test_precheck_rejects_a_panel_drug_named_in_prose_but_not_evaluated() -> None:
    # A SUPPORTED panel drug named in free-text prose but absent from this report's predictions is a
    # fabricated reference (stage-2 second loop). _REPORT does not evaluate trimethoprim-sulfa.
    section = _section(summary="Unlike trimethoprim-sulfamethoxazole, this genome looks clean.")
    ok, reason = deterministic_precheck(section, _REPORT, _NO_RETRIEVAL)
    assert not ok
    assert "trimethoprim-sulfamethoxazole" in reason


def test_percent_regex_binds_only_within_a_line() -> None:
    # #45-A: a digit ending one line and a '%' starting the next must NOT form an N% token, so the
    # reorder differential between the validated and the published string cannot smuggle a percent.
    assert _PERCENT_RE.findall("coverage was 88\n% of the reference") == []
    assert _PERCENT_RE.findall("confidence 88%") == ["88"]
    assert _PERCENT_RE.findall("confidence 88 %") == ["88"]


def test_render_row_emits_exactly_one_percent_token() -> None:
    # drug_report_percents relies on render_row printing exactly one '%' (the confidence). Pin it so
    # a future evidence description carrying a '%' cannot silently widen the per-drug percent set.
    for row in _REPORT.predictions:
        assert len(_PERCENT_RE.findall(render_row(row))) == 1


def test_precheck_rejects_a_per_drug_percent_from_another_drugs_confidence() -> None:
    # 82% is gentamicin's calibrated confidence, present somewhere in the report, so the OLD
    # global membership check accepted it inside meropenem's narrative. Per-drug binding rejects
    # it (#45-B).
    section = _section(
        NLDrugNarrative(
            antibiotic="meropenem", narrative="Meropenem confidence is 82% by the model."
        )
    )
    ok, reason = deterministic_precheck(section, _REPORT, _NO_RETRIEVAL)
    assert not ok
    assert "meropenem" in reason and "82" in reason and "confidence" in reason


def test_precheck_rejects_a_per_drug_percent_equal_to_a_gene_digit() -> None:
    # '2' is a digit of meropenem's own blaKPC-2 evidence (in drug_numbers) but is NOT a confidence
    # (not in drug_report_percents); stating it as '2%' must be rejected -- the OXA-48->48% class.
    section = _section(
        NLDrugNarrative(antibiotic="meropenem", narrative="Support was only 2% of reads.")
    )
    ok, reason = deterministic_precheck(section, _REPORT, _NO_RETRIEVAL)
    assert not ok
    assert "meropenem" in reason and "confidence" in reason


def test_precheck_accepts_a_per_drug_narrative_stating_its_own_confidence() -> None:
    # Positive control: the drug's own rendered confidence percent is a legitimate echo.
    section = _section(
        NLDrugNarrative(antibiotic="meropenem", narrative="Meropenem was called at 99% confidence.")
    )
    ok, _ = deterministic_precheck(section, _REPORT, _NO_RETRIEVAL)
    assert ok


def test_precheck_scopes_citation_numbers_per_drug() -> None:
    from genome_firewall.kb.corpus import KBChunk
    from genome_firewall.kb.retriever import RetrievedChunk

    # A number cited only in meropenem's chunk is allowed in meropenem's narrative but rejected
    # in ceftriaxone's, whose retrieval carries no such number -- per-drug KB scoping (#45-B).
    retrieval = {
        "meropenem": (
            RetrievedChunk(
                chunk=KBChunk(
                    chunk_id="c", gene_family="g", text="assembled at 7777x depth", source="s"
                ),
                score=1.0,
            ),
        )
    }
    ok_mero, _ = deterministic_precheck(
        _section(NLDrugNarrative(antibiotic="meropenem", narrative="Assembled at 7777x depth.")),
        _REPORT,
        retrieval,
    )
    assert ok_mero
    ok_cef, reason = deterministic_precheck(
        _section(NLDrugNarrative(antibiotic="ceftriaxone", narrative="Assembled at 7777x depth.")),
        _REPORT,
        retrieval,
    )
    assert not ok_cef
    assert "ceftriaxone" in reason and "7777" in reason
