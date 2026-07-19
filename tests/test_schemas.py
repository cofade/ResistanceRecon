"""Direct tests for the safety-critical cross-field validators in schemas.py (issue #14).

Most of these models (GateResult, ModelPrediction, ConformalSet, EvidenceItem,
AntibioticPrediction, GenomeReport) are not yet exercised by any other EPIC 2 code --
they exist now so EPIC 3/4 build on a stable contract. That makes their validators
untested by construction unless pinned here directly; several encode P0 safety
invariants (gf-architecture-contract's no-call contract, golden rule #4's disclaimer),
so they are tested here rather than left for a later epic to discover a break in.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from genome_firewall.constants import LAB_CONFIRMATION_DISCLAIMER
from genome_firewall.schemas import (
    AnnotationResult,
    AntibioticPrediction,
    ConformalSet,
    EvidenceItem,
    GateResult,
    GenomeInput,
    GenomeReport,
    ModelFeatureSchema,
    verdict_for_conformal_set,
)


@pytest.mark.parametrize(
    ("labels", "expected"),
    [
        (("S",), "likely_to_work"),
        (("R",), "likely_to_fail"),
        (("S", "R"), "no_call"),
        ((), "no_call"),
    ],
)
def test_verdict_for_conformal_set_matches_the_no_call_contract(labels, expected) -> None:
    assert verdict_for_conformal_set(labels) == expected


def test_genome_report_rejects_a_wrong_disclaimer() -> None:
    with pytest.raises(ValidationError, match="golden rule #4"):
        GenomeReport(genome_id="g1", predictions=(), disclaimer="trust me, it's fine")


def test_genome_report_default_disclaimer_is_the_canonical_constant() -> None:
    report = GenomeReport(genome_id="g1", predictions=())
    assert report.disclaimer == LAB_CONFIRMATION_DISCLAIMER


def test_antibiotic_prediction_rejects_verdict_conformal_set_mismatch() -> None:
    with pytest.raises(ValidationError, match="inconsistent with conformal_set"):
        AntibioticPrediction(
            antibiotic="meropenem",
            verdict="likely_to_work",
            calibrated_confidence=0.9,
            evidence_category="statistical_association",
            supporting_features=("blaKPC-3",),
            conformal_set=ConformalSet(labels=("R",), alpha=0.1),
        )


def test_antibiotic_prediction_accepts_consistent_verdict_and_conformal_set() -> None:
    prediction = AntibioticPrediction(
        antibiotic="meropenem",
        verdict="likely_to_fail",
        calibrated_confidence=0.95,
        evidence_category="statistical_association",
        supporting_features=("blaKPC-3",),
        conformal_set=ConformalSet(labels=("R",), alpha=0.1),
    )
    assert prediction.verdict == "likely_to_fail"


def test_antibiotic_prediction_requires_evidence_when_category_is_not_no_signal() -> None:
    with pytest.raises(ValidationError, match="requires non-empty"):
        AntibioticPrediction(
            antibiotic="meropenem",
            verdict="no_call",
            calibrated_confidence=0.5,
            evidence_category="known_mechanism",
            supporting_features=(),
        )


def test_antibiotic_prediction_allows_empty_evidence_for_no_signal() -> None:
    prediction = AntibioticPrediction(
        antibiotic="meropenem",
        verdict="no_call",
        calibrated_confidence=0.5,
        evidence_category="no_signal",
        supporting_features=(),
    )
    assert prediction.evidence_category == "no_signal"


def test_gate_result_requires_rule_and_verdict_when_fired() -> None:
    with pytest.raises(ValidationError, match="fired=True requires"):
        GateResult(fired=True)


def test_gate_result_rejects_rule_when_not_fired() -> None:
    with pytest.raises(ValidationError, match="fired=False must not carry"):
        GateResult(fired=False, rule="carbapenemase_present", forced_verdict="likely_to_fail")


def test_conformal_set_rejects_repeated_labels() -> None:
    with pytest.raises(ValidationError, match="must not repeat"):
        ConformalSet(labels=("S", "S"), alpha=0.1)


def test_annotation_result_ok_requires_data() -> None:
    with pytest.raises(ValidationError, match="ok=True requires data"):
        AnnotationResult(ok=True, source="mock:test")


def test_annotation_result_failure_requires_error() -> None:
    with pytest.raises(ValidationError, match="ok=False requires error"):
        AnnotationResult(ok=False, source="mock:test")


def test_annotation_result_rejects_ok_true_with_an_error() -> None:
    with pytest.raises(ValidationError, match="ok=True must not carry an error"):
        AnnotationResult(ok=True, source="mock:test", data=(), error="but also this failed?")


def test_annotation_result_rejects_ok_false_with_data() -> None:
    with pytest.raises(ValidationError, match="ok=False must not carry data"):
        AnnotationResult(ok=False, source="mock:test", error="boom", data=())


def test_gate_result_accepts_fired_true_with_rule_and_verdict() -> None:
    gate = GateResult(fired=True, rule="carbapenemase_present", forced_verdict="likely_to_fail")
    assert gate.forced_verdict == "likely_to_fail"


def test_gate_result_accepts_fired_false_without_rule() -> None:
    gate = GateResult(fired=False)
    assert gate.rule is None
    assert gate.forced_verdict is None


def test_antibiotic_prediction_rejects_a_category_not_backed_by_any_cited_item() -> None:
    with pytest.raises(ValidationError, match="is not backed by any cited"):
        AntibioticPrediction(
            antibiotic="meropenem",
            verdict="likely_to_fail",
            calibrated_confidence=0.95,
            evidence_category="known_mechanism",
            supporting_features=("blaKPC-3",),
            evidence=(
                EvidenceItem(
                    description="SHAP signal on blaKPC-3",
                    source="model",
                    evidence_category="statistical_association",
                ),
            ),
        )


def test_antibiotic_prediction_accepts_a_category_backed_by_a_cited_item() -> None:
    prediction = AntibioticPrediction(
        antibiotic="meropenem",
        verdict="likely_to_fail",
        calibrated_confidence=0.95,
        evidence_category="known_mechanism",
        supporting_features=("blaKPC-3",),
        evidence=(
            EvidenceItem(
                description="blaKPC-3 carbapenemase detected",
                source="annotation",
                evidence_category="known_mechanism",
            ),
        ),
    )
    assert prediction.evidence_category == "known_mechanism"


def test_model_feature_schema_accepts_an_ordered_unique_vocabulary() -> None:
    schema = ModelFeatureSchema(
        schema_version="1.0.0",
        amrfinder_db_version="2026-05-15.1",
        engineered_feature_spec_version="1",
        feature_names=("blaKPC-2", "gyrA_S83Y", "has_carbapenemase"),
        vocabulary_sha256="0" * 64,
    )
    assert schema.feature_names[0] == "blaKPC-2"


def test_model_feature_schema_rejects_duplicate_feature_names() -> None:
    with pytest.raises(ValidationError, match="must not contain duplicates"):
        ModelFeatureSchema(
            schema_version="1.0.0",
            amrfinder_db_version="2026-05-15.1",
            engineered_feature_spec_version="1",
            feature_names=("blaKPC-2", "blaKPC-2"),
            vocabulary_sha256="0" * 64,
        )


def test_models_reject_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        GenomeInput.model_validate(
            {
                "genome_id": "g1",
                "species": "Klebsiella pneumoniae",
                "contigs": [{"contig_id": "c1", "length": 100}],
                "unexpected_field": "should be rejected",
            }
        )


def test_models_are_frozen() -> None:
    contig = {"contig_id": "c1", "length": 100}
    genome = GenomeInput(genome_id="g1", species="Klebsiella pneumoniae", contigs=(contig,))
    with pytest.raises(ValidationError):
        genome.genome_id = "g2"  # type: ignore[misc]
