"""Integration-test shape #4 (crosscutting-concepts): prediction primitives -> a complete
GenomeReport whose evidence_category honestly separates KNOWN_MECHANISM from
STATISTICAL_ASSOCIATION and that carries the disclaimer. Driven by the shared synthetic
cohort (no Docker, no network, no LLM).
"""

from __future__ import annotations

import pytest

from genome_firewall.constants import (
    KNOWN_MECHANISM_CONFIDENCE,
    LAB_CONFIRMATION_DISCLAIMER,
)
from genome_firewall.report.builder import build_report
from genome_firewall.report.inputs import DrugPredictionInput, GenomePredictionInputs
from genome_firewall.report.narrative import render_deterministic_narrative
from genome_firewall.schemas import ConformalSet, ModelPrediction
from tests.predictor.conftest import make_synthetic_cohort


@pytest.mark.integration
def test_prediction_primitives_build_a_complete_grounded_report() -> None:
    vectors, labels, _ = make_synthetic_cohort()
    by_id = {v.genome_id: v for v in vectors}
    # g000 (within-ST index 0) carries both blaKPC-2 (meropenem gate) and aac(3)-IIa (gentamicin).
    gid = "g000"
    assert labels["meropenem"][gid] == "R"
    assert labels["gentamicin"][gid] == "R"

    inputs = GenomePredictionInputs(
        genome_id=gid,
        drugs=(
            DrugPredictionInput(antibiotic="meropenem", vector=by_id[gid]),  # gate fires
            DrugPredictionInput(
                antibiotic="gentamicin",
                vector=by_id[gid],
                model_prediction=ModelPrediction(probability_resistant=0.88, model_version="lr-v1"),
                conformal_set=ConformalSet(labels=("R",), alpha=0.1),
                model_top_features=("eng:has_ame",),
            ),
            # ceftriaxone: the carbapenemase hydrolyses cephalosporins -> gate fires
            DrugPredictionInput(antibiotic="ceftriaxone", vector=by_id[gid]),
        ),
    )

    report = build_report(inputs)
    rows = {p.antibiotic: p for p in report.predictions}

    # Meropenem: deterministic known-mechanism gate fired.
    assert rows["meropenem"].verdict == "likely_to_fail"
    assert rows["meropenem"].evidence_category == "known_mechanism"
    assert rows["meropenem"].calibrated_confidence == KNOWN_MECHANISM_CONFIDENCE
    assert any("blaKPC-2" in item.source for item in rows["meropenem"].evidence)

    # Gentamicin: model-driven verdict, known-mechanism evidence (AME is a KB member).
    assert rows["gentamicin"].verdict == "likely_to_fail"
    assert rows["gentamicin"].evidence_category == "known_mechanism"
    assert rows["gentamicin"].calibrated_confidence == 0.88

    # Ceftriaxone: the carbapenemase hydrolyses cephalosporins too, so the gate correctly
    # calls it resistant rather than leaving it to the model (mechanisms.py cross-coverage).
    assert rows["ceftriaxone"].verdict == "likely_to_fail"
    assert rows["ceftriaxone"].evidence_category == "known_mechanism"

    # A clean genome (no carbapenemase / cephalosporinase) is an honest no_signal susceptible call.
    clean = "g004"
    assert labels["meropenem"][clean] == "S"
    clean_report = build_report(
        GenomePredictionInputs(
            genome_id=clean,
            drugs=(
                DrugPredictionInput(
                    antibiotic="ceftriaxone",
                    vector=by_id[clean],
                    model_prediction=ModelPrediction(
                        probability_resistant=0.05, model_version="lr-v1"
                    ),
                    conformal_set=ConformalSet(labels=("S",), alpha=0.1),
                ),
            ),
        )
    )
    ceftriaxone_clean = clean_report.predictions[0]
    assert ceftriaxone_clean.verdict == "likely_to_work"
    assert ceftriaxone_clean.evidence_category == "no_signal"

    # The disclaimer is present on the report and rendered verbatim in the narrative.
    assert report.disclaimer == LAB_CONFIRMATION_DISCLAIMER
    assert LAB_CONFIRMATION_DISCLAIMER in render_deterministic_narrative(report)
