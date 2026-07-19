"""Tests for feature vocabulary + engineered combination features."""

from __future__ import annotations

from typing import Any

from genome_firewall.features.vocabulary import (
    ENGINEERED_FEATURE_NAMES,
    ENGINEERED_PREFIX,
    build_vocabulary,
    engineered_features,
)
from genome_firewall.schemas import GenomeFeatureVector, ModelFeatureSchema


def _vector(**kwargs: Any) -> GenomeFeatureVector:
    base: dict[str, Any] = {
        "genome_id": "g1",
        "schema_version": "1.0.0",
        "amrfinder_db_version": "2026-05-15.1",
    }
    base.update(kwargs)
    return GenomeFeatureVector(**base)


def test_engineered_features_encode_combinations() -> None:
    v = _vector(
        gene_presence={"blaKPC-2": True, "qnrB1": True, "armA": True, "sul1": True},
        gene_drug_subclass={"blaKPC-2": "CARBAPENEM"},
        point_mutations={"gyrA_S83Y": True, "parC_S80I": True},
        point_mutation_disrupt={"ompK36_fs": True},
    )
    eng = engineered_features(v)
    assert eng["n_qrdr_mutations"] == 2.0
    assert eng["has_pmqr"] == 1.0
    assert eng["has_rmtase"] == 1.0
    assert eng["has_carbapenemase"] == 1.0
    assert eng["has_esbl_or_ampc"] == 0.0
    assert eng["has_sul"] == 1.0
    assert eng["has_dfr"] == 0.0
    assert eng["porin_disrupted"] == 1.0


def test_build_vocabulary_is_ordered_hashed_and_engineered_suffixed() -> None:
    v1 = _vector(
        genome_id="g1", gene_presence={"blaKPC-2": True}, point_mutations={"gyrA_S83Y": True}
    )
    v2 = _vector(genome_id="g2", gene_presence={"sul1": True, "blaKPC-2": True})
    schema = build_vocabulary([v1, v2], amrfinder_db_version="2026-05-15.1")
    assert isinstance(schema, ModelFeatureSchema)
    # genes sorted, then mutations, then engineered columns (all eng:-prefixed)
    assert schema.feature_names[:3] == ("blaKPC-2", "sul1", "gyrA_S83Y")
    assert schema.feature_names[-len(ENGINEERED_FEATURE_NAMES) :] == ENGINEERED_FEATURE_NAMES
    assert all(name.startswith(ENGINEERED_PREFIX) for name in ENGINEERED_FEATURE_NAMES)
    assert len(schema.vocabulary_sha256) == 64


def test_build_vocabulary_is_deterministic() -> None:
    v = _vector(gene_presence={"blaKPC-2": True, "sul1": True})
    a = build_vocabulary([v], amrfinder_db_version="2026-05-15.1")
    b = build_vocabulary([v], amrfinder_db_version="2026-05-15.1")
    assert a.feature_names == b.feature_names
    assert a.vocabulary_sha256 == b.vocabulary_sha256
