"""Unit tests for the narrative pipeline: accepted / rejected / disabled, all disclaimer-safe."""

from __future__ import annotations

import pytest

from genome_firewall.constants import LAB_CONFIRMATION_DISCLAIMER
from genome_firewall.llm.mock import MockLLMClient
from genome_firewall.report.builder import build_report
from genome_firewall.report.nl_schemas import NLDrugNarrative, NLReportSection, ReportVerdict
from genome_firewall.report.pipeline import narrate_report
from tests.report.conftest import make_prediction_inputs

_REPORT = build_report(make_prediction_inputs("g1"))

_GROUNDED = NLReportSection(
    summary="Decision support summary.",
    per_antibiotic=(
        NLDrugNarrative(antibiotic="meropenem", narrative="Meropenem is LIKELY TO FAIL."),
        NLDrugNarrative(antibiotic="ceftriaxone", narrative="Ceftriaxone is LIKELY TO WORK."),
    ),
)


def _client(narrative: NLReportSection, *, judge_pass: bool) -> MockLLMClient:
    return MockLLMClient(
        {
            "report_narrative": narrative,
            "report_review": ReportVerdict(grounding_score=1.0, overall_pass=judge_pass),
        }
    )


def test_accepted_path_serves_the_llm_narrative() -> None:
    env = narrate_report(_REPORT, client=_client(_GROUNDED, judge_pass=True))
    assert env.review_status == "llm_output_accepted"
    assert env.source == "llm"
    assert "Meropenem is LIKELY TO FAIL" in (env.report.narrative_summary or "")
    assert LAB_CONFIRMATION_DISCLAIMER in (env.report.narrative_summary or "")


def test_llm_disclaimer_caveat_is_not_duplicated() -> None:
    """An LLM that helpfully restates the disclaimer as a caveat must not yield two disclaimers:
    the canonical one is appended once and the near-duplicate caveat is dropped (golden rule #4)."""
    narrative = NLReportSection(
        summary="Decision support summary.",
        per_antibiotic=(
            NLDrugNarrative(antibiotic="meropenem", narrative="Meropenem is LIKELY TO FAIL."),
        ),
        caveats=("Confirm all results with standard laboratory susceptibility testing.",),
    )
    env = narrate_report(_REPORT, client=_client(narrative, judge_pass=True))
    assert env.source == "llm"
    summary = env.report.narrative_summary or ""
    assert summary.count(LAB_CONFIRMATION_DISCLAIMER) == 1
    assert summary.count("susceptibility testing") == 1


def test_judge_rejection_fails_closed_to_template() -> None:
    env = narrate_report(_REPORT, client=_client(_GROUNDED, judge_pass=False))
    assert env.review_status == "llm_output_rejected"
    assert env.source == "template"
    assert env.report.narrative_summary == _deterministic(_REPORT)
    assert LAB_CONFIRMATION_DISCLAIMER in (env.report.narrative_summary or "")


def test_precheck_rejection_fails_closed_to_template() -> None:
    fabricated = NLReportSection(summary="Resistance is 91% likely.", per_antibiotic=())
    env = narrate_report(_REPORT, client=_client(fabricated, judge_pass=True))
    assert env.review_status == "llm_output_rejected"
    assert env.source == "template"
    assert env.error is not None


def test_narrator_llm_error_fails_closed_to_template() -> None:
    # Mock has no "report_narrative" script -> LLMRefusalError -> template.
    env = narrate_report(_REPORT, client=MockLLMClient({}))
    assert env.review_status == "llm_output_rejected"
    assert env.source == "template"


def test_no_client_is_llm_disabled_deterministic() -> None:
    env = narrate_report(_REPORT, client=None)
    assert env.review_status == "llm_disabled"
    assert env.source == "template"
    assert env.report.narrative_summary == _deterministic(_REPORT)


def test_a_distinct_lab_caveat_is_preserved_not_dropped() -> None:
    # #45-C: a *distinct* clinical hedge that merely mentions the lab must survive, not be
    # dropped by an over-broad disclaimer-dedup. Two shapes: 'confirmed' (a word-boundary miss)
    # and a specific call that pairs 'susceptibility testing' with no 'result'.
    narrative = NLReportSection(
        summary="Decision support summary.",
        per_antibiotic=(
            NLDrugNarrative(antibiotic="meropenem", narrative="Meropenem is LIKELY TO FAIL."),
        ),
        caveats=(
            "Coverage over the blaKPC locus was low, so the carbapenemase allele could not be "
            "confirmed; laboratory re-testing is advised.",
            "Confirm the porin-disruption call by phenotypic susceptibility testing.",
        ),
    )
    env = narrate_report(_REPORT, client=_client(narrative, judge_pass=True))
    assert env.source == "llm"
    summary = env.report.narrative_summary or ""
    assert "blaKPC locus" in summary
    assert "porin-disruption call" in summary


def test_a_laboratory_testing_restatement_is_still_deduplicated() -> None:
    # #45-C guard: the committed narrator_grounded.json caveat says 'laboratory testing' (not the
    # exact 'susceptibility testing'); it must STILL be dropped or the appended disclaimer doubles.
    narrative = NLReportSection(
        summary="Decision support summary.",
        per_antibiotic=(
            NLDrugNarrative(antibiotic="meropenem", narrative="Meropenem is LIKELY TO FAIL."),
        ),
        caveats=("This is decision support only; confirm every result with laboratory testing.",),
    )
    env = narrate_report(_REPORT, client=_client(narrative, judge_pass=True))
    assert env.source == "llm"
    summary = env.report.narrative_summary or ""
    assert summary.count(LAB_CONFIRMATION_DISCLAIMER) == 1
    assert "laboratory testing." not in summary


def test_flattened_output_forms_no_percent_the_precheck_missed() -> None:
    import re

    from genome_firewall.kb.corpus import KBChunk
    from genome_firewall.kb.retriever import RetrievedChunk
    from genome_firewall.report.pipeline import _flatten
    from genome_firewall.report.reviewer import _PERCENT_RE, deterministic_precheck

    # #45-A end-to-end: a per-drug narrative ending in a bare KB digit (88, cited for meropenem),
    # plus a caveat starting with '%'. The digit and '%' land adjacent across the newline join,
    # but the intra-line _PERCENT_RE forms no 88% token -- what the OLD `\s*%` pattern would match.
    retrieval = {
        "meropenem": (
            RetrievedChunk(
                chunk=KBChunk(
                    chunk_id="c", gene_family="g", text="region near 88 coverage", source="s"
                ),
                score=1.0,
            ),
        )
    }
    section = NLReportSection(
        summary="Decision support summary.",
        per_antibiotic=(
            NLDrugNarrative(antibiotic="meropenem", narrative="Closest-reference identity 88"),
        ),
        caveats=("% figures below are approximate.",),
    )
    ok, _ = deterministic_precheck(section, _REPORT, retrieval)
    assert ok
    flattened = _flatten(section, _REPORT)
    assert "88\n%" in flattened
    assert re.compile(r"(\d+(?:\.\d+)?)\s*%").findall(flattened) == ["88"]
    assert _PERCENT_RE.findall(flattened) == []


def test_tripwire_fails_closed_if_flatten_emits_an_ungrounded_percent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The #45-A tripwire is defensive: a passing pre-check already guarantees grounded percents, so
    # it cannot fire through the front door. Simulate a future _flatten regression that reintroduces
    # an ungrounded percent (77% is absent from _REPORT) and assert narrate_report fails closed.
    import genome_firewall.report.pipeline as pipeline_mod

    monkeypatch.setattr(
        pipeline_mod, "_flatten", lambda section, report: "Meropenem confidence is 77%."
    )
    env = narrate_report(_REPORT, client=_client(_GROUNDED, judge_pass=True))
    assert env.review_status == "llm_output_rejected"
    assert env.source == "template"
    assert env.error is not None and "percent" in env.error
    assert env.report.narrative_summary == _deterministic(_REPORT)


def _deterministic(report: object) -> str:
    from genome_firewall.report.narrative import render_deterministic_narrative

    return render_deterministic_narrative(report)  # type: ignore[arg-type]
