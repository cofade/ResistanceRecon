"""Unit tests for the deterministic report builder (issue #23)."""

from __future__ import annotations

from genome_firewall.constants import KNOWN_MECHANISM_CONFIDENCE, LAB_CONFIRMATION_DISCLAIMER
from genome_firewall.report.builder import build_report
from genome_firewall.report.inputs import DrugPredictionInput, GenomePredictionInputs
from genome_firewall.schemas import ConformalSet, ModelPrediction
from tests.report.conftest import (
    ceftriaxone_susceptible_input,
    ciprofloxacin_insufficient_input,
    gentamicin_model_input,
    make_prediction_inputs,
    meropenem_gate_input,
    vector,
)


def _row(inputs: DrugPredictionInput):
    report = build_report(GenomePredictionInputs(genome_id="g1", drugs=(inputs,)))
    return report.predictions[0]


def test_gate_fired_row_is_forced_fail_at_known_mechanism_confidence() -> None:
    row = _row(meropenem_gate_input())
    assert row.verdict == "likely_to_fail"
    assert row.calibrated_confidence == KNOWN_MECHANISM_CONFIDENCE
    assert row.evidence_category == "known_mechanism"
    assert row.conformal_set is None  # gate short-circuits the model
    assert row.target_present is True


def test_model_row_takes_verdict_from_conformal_and_confidence_from_model() -> None:
    row = _row(gentamicin_model_input())
    assert row.verdict == "likely_to_fail"  # conformal {R}
    assert row.calibrated_confidence == 0.82  # probability_resistant
    assert row.conformal_set is not None
    assert row.evidence_category == "known_mechanism"  # AME is a KB member


def test_susceptible_row_is_likely_to_work_with_no_signal() -> None:
    row = _row(ceftriaxone_susceptible_input())
    assert row.verdict == "likely_to_work"
    assert row.calibrated_confidence == 0.96  # 1 - 0.04
    assert row.evidence_category == "no_signal"
    assert row.supporting_features == ()


def test_insufficient_data_is_a_no_call() -> None:
    row = _row(ciprofloxacin_insufficient_input())
    assert row.verdict == "no_call"
    assert row.calibrated_confidence == 0.0
    assert row.evidence_category == "no_signal"
    assert row.target_present is True  # a panel drug, just under-powered


def test_off_panel_antibiotic_is_a_no_call_with_target_present_none() -> None:
    row = _row(DrugPredictionInput(antibiotic="colistin", vector=vector()))
    assert row.verdict == "no_call"
    assert row.target_present is None
    assert row.evidence_category == "no_signal"


def test_model_row_without_conformal_set_abstains() -> None:
    row = _row(
        DrugPredictionInput(
            antibiotic="ceftriaxone",
            vector=vector(),
            model_prediction=ModelPrediction(probability_resistant=0.9, model_version="lr-v1"),
        )
    )
    assert row.verdict == "no_call"
    assert row.evidence_category == "no_signal"


def test_no_call_confidence_reflects_model_leaning() -> None:
    row = _row(
        DrugPredictionInput(
            antibiotic="ceftriaxone",
            vector=vector(),
            model_prediction=ModelPrediction(probability_resistant=0.7, model_version="lr-v1"),
            conformal_set=ConformalSet(labels=("S", "R"), alpha=0.1),  # ambiguous -> no_call
        )
    )
    assert row.verdict == "no_call"
    assert row.calibrated_confidence == 0.7  # max(0.7, 0.3)


def test_build_report_propagates_genome_id_and_disclaimer() -> None:
    report = build_report(make_prediction_inputs("573.10001"))
    assert report.genome_id == "573.10001"
    assert report.disclaimer == LAB_CONFIRMATION_DISCLAIMER
    assert len(report.predictions) == 4
    assert report.narrative_summary is None
