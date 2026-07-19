"""Unit tests for the narrative pipeline: accepted / rejected / disabled, all disclaimer-safe."""

from __future__ import annotations

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


def _deterministic(report: object) -> str:
    from genome_firewall.report.narrative import render_deterministic_narrative

    return render_deterministic_narrative(report)  # type: ignore[arg-type]
