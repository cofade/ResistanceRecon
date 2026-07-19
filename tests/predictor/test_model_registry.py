"""Model registry round-trip + versioning (issue #22): save -> load reproduces the schema,
conformal thresholds, signed coefficients, and calibrated probabilities; registry.json drives
PredictorRegistry.load. Offline, deterministic."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from genome_firewall.features.feature_matrix import assemble_feature_matrix
from genome_firewall.features.vocabulary import build_vocabulary
from genome_firewall.predictor.calibration import predict_resistant_proba
from genome_firewall.predictor.conformal import fit_conformal
from genome_firewall.predictor.model_registry import (
    STATUS_INSUFFICIENT,
    STATUS_TRAINED,
    PredictorRegistry,
    RegistryEntry,
    drug_slug,
    latest_version,
    load_drug_model,
    save_drug_model,
    write_registry,
)
from genome_firewall.predictor.train import train_one_antibiotic
from tests.predictor.conftest import SyntheticCohort


def _trained_gentamicin(cohort: SyntheticCohort):  # type: ignore[no-untyped-def]
    vectors, labels, metadata = cohort
    schema = build_vocabulary(vectors, amrfinder_db_version="2026-05-15.1")
    matrix = assemble_feature_matrix(vectors, schema)
    result = train_one_antibiotic(
        matrix, labels["gentamicin"], metadata, antibiotic="gentamicin", feature_schema=schema
    )
    assert result.status == STATUS_TRAINED
    artifact = fit_conformal([0.9, 0.8, 0.1, 0.2] * 10, [1, 1, 0, 0] * 10, alpha=0.10)
    return result, artifact, matrix, schema


def test_drug_slug_preserves_tmp_smx() -> None:
    assert drug_slug("trimethoprim-sulfamethoxazole") == "trimethoprim-sulfamethoxazole"
    assert drug_slug("Ceftriaxone") == "ceftriaxone"


def test_save_load_round_trip(synthetic_cohort: SyntheticCohort, tmp_path: Path) -> None:
    result, artifact, matrix, schema = _trained_gentamicin(synthetic_cohort)
    version = save_drug_model(tmp_path, result, artifact)
    assert version == "v1"

    loaded = load_drug_model(tmp_path, "gentamicin", version="latest")
    assert loaded.feature_schema.vocabulary_sha256 == schema.vocabulary_sha256
    assert loaded.conformal.tau_r == artifact.tau_r
    assert loaded.coefficients == result.coefficients
    # The persisted calibrated model reproduces the same probabilities.
    x = matrix.to_numpy(dtype=np.float64)[:4]
    original = predict_resistant_proba(result.calibrated_model, x)
    restored = predict_resistant_proba(loaded.calibrated_model, x)
    assert np.allclose(original, restored)


def test_versioning_increments(synthetic_cohort: SyntheticCohort, tmp_path: Path) -> None:
    result, artifact, _matrix, _schema = _trained_gentamicin(synthetic_cohort)
    assert save_drug_model(tmp_path, result, artifact) == "v1"
    assert save_drug_model(tmp_path, result, artifact) == "v2"
    assert latest_version(tmp_path, "gentamicin") == "v2"


def test_registry_load_reflects_statuses(synthetic_cohort: SyntheticCohort, tmp_path: Path) -> None:
    result, artifact, _matrix, schema = _trained_gentamicin(synthetic_cohort)
    version = save_drug_model(tmp_path, result, artifact)
    entries = {
        "gentamicin": RegistryEntry(status=STATUS_TRAINED, latest_version=version),
        "ciprofloxacin": RegistryEntry(
            status=STATUS_INSUFFICIENT, latest_version=None, reason="insufficient data: thin"
        ),
    }
    write_registry(tmp_path, entries, base_schema=schema)

    registry = PredictorRegistry.load(tmp_path)
    assert registry.amrfinder_db_version == "2026-05-15.1"
    assert registry.status("gentamicin") == STATUS_TRAINED
    assert registry.get("gentamicin") is not None
    assert registry.status("ciprofloxacin") == STATUS_INSUFFICIENT
    assert registry.get("ciprofloxacin") is None
    assert "thin" in (registry.reason("ciprofloxacin") or "")


def test_model_card_written(synthetic_cohort: SyntheticCohort, tmp_path: Path) -> None:
    result, artifact, _matrix, _schema = _trained_gentamicin(synthetic_cohort)
    save_drug_model(tmp_path, result, artifact)
    card = (tmp_path / drug_slug("gentamicin") / "v1" / "model_card.md").read_text()
    assert "laboratory" in card.lower()  # the mandatory confirmation caveat
    assert "gentamicin" in card.lower()
