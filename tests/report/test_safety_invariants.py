"""Cross-cutting safety-invariant tests for the report/LLM surface (P0 if absent)."""

from __future__ import annotations

import importlib

from genome_firewall.constants import LAB_CONFIRMATION_DISCLAIMER
from genome_firewall.llm.mock import MockLLMClient
from genome_firewall.report.builder import build_report
from genome_firewall.report.inputs import DrugPredictionInput, GenomePredictionInputs
from genome_firewall.report.nl_schemas import NLDrugNarrative, NLReportSection, ReportVerdict
from genome_firewall.report.pipeline import narrate_report
from tests.report.conftest import (
    ceftriaxone_susceptible_input,
    ciprofloxacin_insufficient_input,
    gentamicin_model_input,
    meropenem_gate_input,
    vector,
)

_ALL_DRUGS = GenomePredictionInputs(
    genome_id="g1",
    drugs=(
        meropenem_gate_input(),
        gentamicin_model_input(),
        ceftriaxone_susceptible_input(),
        ciprofloxacin_insufficient_input(),
        DrugPredictionInput(antibiotic="colistin", vector=vector()),  # off-panel
    ),
)


def test_disclaimer_present_on_every_narrative_path() -> None:
    report = build_report(_ALL_DRUGS)
    grounded = NLReportSection(
        summary="Summary.",
        per_antibiotic=(
            NLDrugNarrative(antibiotic="meropenem", narrative="Meropenem is LIKELY TO FAIL."),
        ),
    )

    accepted = narrate_report(
        report,
        client=MockLLMClient(
            {
                "report_narrative": grounded,
                "report_review": ReportVerdict(grounding_score=1.0, overall_pass=True),
            }
        ),
    )
    rejected = narrate_report(
        report,
        client=MockLLMClient(
            {
                "report_narrative": grounded,
                "report_review": ReportVerdict(grounding_score=0.0, overall_pass=False),
            }
        ),
    )
    disabled = narrate_report(report, client=None)

    for env in (accepted, rejected, disabled):
        assert env.report.disclaimer == LAB_CONFIRMATION_DISCLAIMER
        assert LAB_CONFIRMATION_DISCLAIMER in (env.report.narrative_summary or "")


def test_off_panel_and_insufficient_rows_are_no_signal_no_call() -> None:
    report = build_report(_ALL_DRUGS)
    rows = {p.antibiotic: p for p in report.predictions}
    for drug in ("colistin", "ciprofloxacin"):
        assert rows[drug].verdict == "no_call"
        assert rows[drug].evidence_category == "no_signal"


def test_import_boundary_gate_still_holds() -> None:
    # report/ and kb/ importing llm/ is allowed; the prediction path must stay LLM-free.
    module = importlib.import_module("check_import_boundary")
    assert module.main() == 0


def test_narrative_envelope_carries_no_verdict_field() -> None:
    from genome_firewall.report.pipeline import NarrativeEnvelope

    forbidden = {"verdict", "calibrated_confidence", "probability_resistant", "sir"}
    assert forbidden.isdisjoint(NarrativeEnvelope.model_fields)
