"""PR-A end-to-end integration test (issue #20): synthetic feature matrix -> split -> gate
-> train + calibration. Offline; no Docker, no network."""

from __future__ import annotations

import pytest

from genome_firewall.features.feature_matrix import assemble_feature_matrix
from genome_firewall.features.vocabulary import build_vocabulary
from genome_firewall.predictor.target_gate import evaluate_gate
from genome_firewall.predictor.train import train_one_antibiotic
from tests.predictor.conftest import SyntheticCohort


@pytest.mark.integration
def test_pra_pipeline_trains_a_model_drug_and_flags_the_thin_drug(
    synthetic_cohort: SyntheticCohort,
) -> None:
    vectors, labels, metadata = synthetic_cohort
    schema = build_vocabulary(vectors, amrfinder_db_version="2026-05-15.1")
    matrix = assemble_feature_matrix(vectors, schema)

    # gentamicin: resistance is driven by an AME the gate never fires on, so the calibrated
    # model must learn it -> high resistant-recall on the grouped test fold.
    gate_positive = {v.genome_id: evaluate_gate("gentamicin", v).result.fired for v in vectors}
    result = train_one_antibiotic(
        matrix,
        labels["gentamicin"],
        metadata,
        antibiotic="gentamicin",
        feature_schema=schema,
        gate_positive=gate_positive,
    )
    assert result.status == "trained"
    assert result.calibrated_model is not None
    assert result.metrics is not None and result.metrics.test_marginal is not None
    assert result.metrics.test_marginal.resistant_recall >= 0.8
    # the model's own top coefficients should implicate the AME signal (statistical evidence)
    top_features = {coefficient.feature for coefficient in result.coefficients[:5]}
    assert "aac(3)-IIa" in top_features or "eng:has_ame" in top_features

    # ciprofloxacin is deliberately thin -> min-n gate -> insufficient data, no model
    thin = train_one_antibiotic(
        matrix,
        labels["ciprofloxacin"],
        metadata,
        antibiotic="ciprofloxacin",
        feature_schema=schema,
    )
    assert thin.status == "insufficient_data"
    assert thin.calibrated_model is None
