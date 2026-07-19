"""predict.py unit tests (issue #22): gate authority (one-directional, short-circuits the
model), typed compatibility errors, and honest no_call for an untrained drug. Offline."""

from __future__ import annotations

import numpy as np
import pytest

from genome_firewall.constants import KNOWN_MECHANISM_CONFIDENCE
from genome_firewall.predictor.conformal import ConformalArtifact
from genome_firewall.predictor.errors import (
    AmrfinderDbVersionMismatchError,
    FeatureSchemaMismatchError,
)
from genome_firewall.predictor.model_registry import (
    STATUS_INSUFFICIENT,
    STATUS_TRAINED,
    DrugModel,
    PredictorRegistry,
    RegistryEntry,
)
from genome_firewall.predictor.predict import (
    _check_compatibility,
    predict_antibiotic,
    predict_genome,
)
from genome_firewall.predictor.train import SignedCoefficient
from genome_firewall.schemas import GenomeFeatureVector, ModelFeatureSchema

_DB = "2026-05-15.1"
_SCHEMA_V = "1.0.0"


class _ExplodingModel:
    """A stand-in calibrated model that must NEVER be consulted when the gate fires."""

    classes_ = np.array([0, 1])

    def predict_proba(self, x: object) -> object:
        raise AssertionError("the model must not be consulted once the deterministic gate fires")


def _schema() -> ModelFeatureSchema:
    return ModelFeatureSchema(
        schema_version=_SCHEMA_V,
        amrfinder_db_version=_DB,
        engineered_feature_spec_version="1",
        feature_names=("blaKPC-2", "aac(3)-IIa", "eng:has_carbapenemase"),
        vocabulary_sha256="deadbeef",
    )


def _artifact() -> ConformalArtifact:
    return ConformalArtifact(
        alpha=0.1,
        tau_s=0.5,
        tau_r=0.5,
        n_cal_susceptible=50,
        n_cal_resistant=50,
        guarantee_available=True,
    )


def _registry_with_exploding_meropenem() -> PredictorRegistry:
    model = DrugModel(
        antibiotic="meropenem",
        version="v1",
        calibrated_model=_ExplodingModel(),
        feature_schema=_schema(),
        conformal=_artifact(),
        coefficients=(),
    )
    return PredictorRegistry(
        amrfinder_db_version=_DB,
        schema_version=_SCHEMA_V,
        engineered_feature_spec_version="1",
        entries={"meropenem": RegistryEntry(status=STATUS_TRAINED, latest_version="v1")},
        drugs={"meropenem": model},
    )


def _carbapenemase_vector(*, db: str = _DB, schema_version: str = _SCHEMA_V) -> GenomeFeatureVector:
    return GenomeFeatureVector(
        genome_id="t",
        schema_version=schema_version,
        amrfinder_db_version=db,
        gene_presence={"blaKPC-2": True},
        gene_drug_subclass={"blaKPC-2": "CARBAPENEM"},
    )


def test_gate_short_circuits_the_model() -> None:
    registry = _registry_with_exploding_meropenem()
    prediction = predict_antibiotic(_carbapenemase_vector(), "meropenem", registry)
    # The gate wins over whatever the (exploding) model would say -- and never consults it.
    assert prediction.verdict == "likely_to_fail"
    assert prediction.evidence_category == "known_mechanism"
    assert prediction.calibrated_confidence == KNOWN_MECHANISM_CONFIDENCE
    assert prediction.conformal_set is None
    assert prediction.target_present is True
    assert "blaKPC-2" in prediction.supporting_features


def test_gate_is_one_directional_absence_does_not_force_work() -> None:
    # A carbapenemase-absent genome must NOT be gate-forced to likely_to_work; with no model
    # for that drug it is an honest no_call, never an affirmative 'works'.
    registry = PredictorRegistry(
        amrfinder_db_version=_DB,
        schema_version=_SCHEMA_V,
        engineered_feature_spec_version="1",
        entries={},
        drugs={},
    )
    clean = GenomeFeatureVector(genome_id="t", schema_version=_SCHEMA_V, amrfinder_db_version=_DB)
    prediction = predict_antibiotic(clean, "meropenem", registry)
    assert prediction.verdict == "no_call"
    assert prediction.evidence_category == "no_signal"


def test_no_trained_model_is_no_call() -> None:
    registry = PredictorRegistry(
        amrfinder_db_version=_DB,
        schema_version=_SCHEMA_V,
        engineered_feature_spec_version="1",
        entries={
            "ciprofloxacin": RegistryEntry(
                status=STATUS_INSUFFICIENT, latest_version=None, reason="insufficient data"
            )
        },
        drugs={},
    )
    clean = GenomeFeatureVector(genome_id="t", schema_version=_SCHEMA_V, amrfinder_db_version=_DB)
    prediction = predict_antibiotic(clean, "ciprofloxacin", registry)
    assert prediction.verdict == "no_call"
    assert prediction.evidence_category == "no_signal"
    assert prediction.conformal_set is None


def test_db_version_mismatch_raises() -> None:
    registry = _registry_with_exploding_meropenem()
    with pytest.raises(AmrfinderDbVersionMismatchError):
        predict_genome(_carbapenemase_vector(db="2099-01-01.9"), registry)


def test_schema_version_mismatch_raises() -> None:
    registry = _registry_with_exploding_meropenem()
    with pytest.raises(FeatureSchemaMismatchError):
        predict_genome(_carbapenemase_vector(schema_version="9.9.9"), registry)


def test_novel_gene_is_not_a_mismatch() -> None:
    registry = _registry_with_exploding_meropenem()
    vector = GenomeFeatureVector(
        genome_id="t",
        schema_version=_SCHEMA_V,
        amrfinder_db_version=_DB,
        gene_presence={"blaKPC-2": True, "blaNOVEL-99": True},  # novel gene absent from vocab
        gene_drug_subclass={"blaKPC-2": "CARBAPENEM"},
    )
    # Matching versions + a novel gene is compatible (novel genes are dropped as OOV, not errors).
    _check_compatibility(vector, registry)  # must not raise
    predictions = predict_genome(vector, registry)
    assert len(predictions) == 5  # one row per panel drug


# --- model-path verdict branches (deterministic fixed-probability model, gate never fires) ---


class _FixedModel:
    """A calibrated model that always returns a chosen P(resistant), so each conformal set
    shape -> verdict branch can be exercised deterministically."""

    classes_ = np.array([0, 1])

    def __init__(self, p_resistant: float) -> None:
        self._p = float(p_resistant)

    def predict_proba(self, x: np.ndarray) -> np.ndarray:
        n = x.shape[0]
        return np.column_stack([np.full(n, 1.0 - self._p), np.full(n, self._p)])


def _model(
    p_resistant: float,
    *,
    tau_s: float,
    tau_r: float,
    coefficients: tuple[SignedCoefficient, ...],
    guarantee_available: bool = True,
) -> DrugModel:
    schema = ModelFeatureSchema(
        schema_version=_SCHEMA_V,
        amrfinder_db_version=_DB,
        engineered_feature_spec_version="1",
        feature_names=("driverGene", "protectiveGene"),
        vocabulary_sha256="cafe",
    )
    conformal = ConformalArtifact(
        alpha=0.1,
        tau_s=tau_s,
        tau_r=tau_r,
        n_cal_susceptible=50,
        n_cal_resistant=50,
        guarantee_available=guarantee_available,
    )
    return DrugModel(
        antibiotic="gentamicin",
        version="v1",
        calibrated_model=_FixedModel(p_resistant),
        feature_schema=schema,
        conformal=conformal,
        coefficients=coefficients,
    )


def _registry_for(model: DrugModel) -> PredictorRegistry:
    return PredictorRegistry(
        amrfinder_db_version=_DB,
        schema_version=_SCHEMA_V,
        engineered_feature_spec_version="1",
        entries={"gentamicin": RegistryEntry(status=STATUS_TRAINED, latest_version="v1")},
        drugs={"gentamicin": model},
    )


def _vector(genes: tuple[str, ...]) -> GenomeFeatureVector:
    # No RMTase/carbapenemase symbol -> the gentamicin gate never fires, forcing the model path.
    return GenomeFeatureVector(
        genome_id="t",
        schema_version=_SCHEMA_V,
        amrfinder_db_version=_DB,
        gene_presence=dict.fromkeys(genes, True),
    )


_DRIVER = SignedCoefficient(feature="driverGene", coefficient=3.0)
_PROTECTOR = SignedCoefficient(feature="protectiveGene", coefficient=-2.0)


def test_model_likely_to_fail_cites_drivers() -> None:
    model = _model(0.95, tau_s=0.5, tau_r=0.5, coefficients=(_DRIVER, _PROTECTOR))
    prediction = predict_antibiotic(_vector(("driverGene",)), "gentamicin", _registry_for(model))
    assert prediction.verdict == "likely_to_fail"
    assert prediction.evidence_category == "statistical_association"
    assert prediction.calibrated_confidence == pytest.approx(0.95)
    assert any("toward resistance" in f for f in prediction.supporting_features)


def test_model_likely_to_work_cites_protectors_and_absence() -> None:
    model = _model(0.05, tau_s=0.5, tau_r=0.5, coefficients=(_DRIVER, _PROTECTOR))
    prediction = predict_antibiotic(
        _vector(("protectiveGene",)), "gentamicin", _registry_for(model)
    )
    assert prediction.verdict == "likely_to_work"
    assert prediction.calibrated_confidence == pytest.approx(0.95)
    assert any("toward susceptibility" in f for f in prediction.supporting_features)
    # No positive-weight present feature -> the honest 'no known determinants' note is attached.
    assert any("no known" in f for f in prediction.supporting_features)


def test_model_ambiguous_set_is_no_call_statistical() -> None:
    model = _model(0.5, tau_s=0.6, tau_r=0.6, coefficients=(_DRIVER, _PROTECTOR))
    prediction = predict_antibiotic(_vector(("driverGene",)), "gentamicin", _registry_for(model))
    assert prediction.verdict == "no_call"
    assert prediction.evidence_category == "statistical_association"
    assert prediction.conformal_set is not None
    assert set(prediction.conformal_set.labels) == {"S", "R"}


def test_model_empty_set_is_no_signal() -> None:
    model = _model(0.5, tau_s=0.3, tau_r=0.3, coefficients=(_DRIVER, _PROTECTOR))
    prediction = predict_antibiotic(_vector(("driverGene",)), "gentamicin", _registry_for(model))
    assert prediction.verdict == "no_call"
    assert prediction.evidence_category == "no_signal"
    assert prediction.conformal_set is not None
    assert prediction.conformal_set.labels == ()


def test_guarantee_void_is_surfaced_on_the_verdict() -> None:
    # A model whose conformal finite-sample guarantee is unavailable must SAY so on every
    # affected verdict -- never leave the safeguard visible only in the model card.
    model = _model(
        0.95, tau_s=0.5, tau_r=0.5, coefficients=(_DRIVER, _PROTECTOR), guarantee_available=False
    )
    prediction = predict_antibiotic(_vector(("driverGene",)), "gentamicin", _registry_for(model))
    assert prediction.verdict == "likely_to_fail"
    assert any("UNAVAILABLE" in feature for feature in prediction.supporting_features)


def test_predict_antibiotic_also_fails_loud_on_compat() -> None:
    # The fail-loud guard lives on the public single-drug entry too, not only predict_genome.
    registry = _registry_with_exploding_meropenem()
    with pytest.raises(AmrfinderDbVersionMismatchError):
        predict_antibiotic(_carbapenemase_vector(db="2099-01-01.9"), "meropenem", registry)


def test_full_vector_present_determinant_beyond_top20_is_not_zeroed() -> None:
    # Regression pin for the coefficient-truncation P1: a PRESENT resistance determinant ranked
    # BEYOND the old top-20 display slice must still carry its real weight, so the honest
    # "no known determinants" note is suppressed. A [:20] slice (the original bug) would zero it
    # and falsely declare works-from-absence -- the exact overclaim ADR-0018 forbids.
    names = (*(f"noise{i:02d}" for i in range(25)), "rareDeterminant")
    coefficients = (
        *(SignedCoefficient(feature=f"noise{i:02d}", coefficient=5.0 - i * 0.1) for i in range(25)),
        SignedCoefficient(feature="rareDeterminant", coefficient=0.4),  # positive, ranked last
    )
    schema = ModelFeatureSchema(
        schema_version=_SCHEMA_V,
        amrfinder_db_version=_DB,
        engineered_feature_spec_version="1",
        feature_names=names,
        vocabulary_sha256="cafe",
    )
    conformal = ConformalArtifact(
        alpha=0.1,
        tau_s=0.5,
        tau_r=0.5,
        n_cal_susceptible=50,
        n_cal_resistant=50,
        guarantee_available=True,
    )
    model = DrugModel(
        antibiotic="gentamicin",
        version="v1",
        calibrated_model=_FixedModel(0.05),  # low p -> {S} -> likely_to_work
        feature_schema=schema,
        conformal=conformal,
        coefficients=coefficients,
    )
    vector = GenomeFeatureVector(
        genome_id="t",
        schema_version=_SCHEMA_V,
        amrfinder_db_version=_DB,
        gene_presence={"rareDeterminant": True},  # the one present feature, ranked #26 by |weight|
    )
    prediction = predict_antibiotic(vector, "gentamicin", _registry_for(model))
    assert prediction.verdict == "likely_to_work"
    # The present positive determinant is seen -> the false "no known determinants" note is absent.
    assert not any("no known" in feature for feature in prediction.supporting_features)


def test_engineered_spec_version_mismatch_raises() -> None:
    # Running-code engineered-feature spec differs from the trained model's -> fail loud.
    registry = PredictorRegistry(
        amrfinder_db_version=_DB,
        schema_version=_SCHEMA_V,
        engineered_feature_spec_version="999",  # != the running code's ENGINEERED_SPEC_VERSION
        entries={},
        drugs={},
    )
    clean = GenomeFeatureVector(genome_id="t", schema_version=_SCHEMA_V, amrfinder_db_version=_DB)
    with pytest.raises(FeatureSchemaMismatchError):
        predict_genome(clean, registry)
