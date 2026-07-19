"""Tests for GenomeFeatureVector -> numeric feature-row/matrix mapping."""

from __future__ import annotations

from typing import Any

from genome_firewall.features.feature_matrix import assemble_feature_matrix, build_feature_row
from genome_firewall.features.vocabulary import build_vocabulary
from genome_firewall.schemas import GenomeFeatureVector


def _vector(**kwargs: Any) -> GenomeFeatureVector:
    base: dict[str, Any] = {
        "genome_id": "g1",
        "schema_version": "1.0.0",
        "amrfinder_db_version": "2026-05-15.1",
    }
    base.update(kwargs)
    return GenomeFeatureVector(**base)


def test_feature_row_aligns_to_schema_order() -> None:
    train = _vector(
        gene_presence={"blaKPC-2": True, "sul1": True},
        gene_drug_subclass={"blaKPC-2": "CARBAPENEM"},
    )
    schema = build_vocabulary([train], amrfinder_db_version="2026-05-15.1")
    # a genome carrying only sul1
    row, oov = build_feature_row(_vector(gene_presence={"sul1": True}), schema)
    names = list(schema.feature_names)
    assert row[names.index("sul1")] == 1.0
    assert row[names.index("blaKPC-2")] == 0.0
    assert row[names.index("eng:has_sul")] == 1.0
    assert row[names.index("eng:has_carbapenemase")] == 0.0
    assert oov == 0


def test_feature_row_counts_out_of_vocabulary_genes() -> None:
    train = _vector(gene_presence={"blaKPC-2": True})
    schema = build_vocabulary([train], amrfinder_db_version="2026-05-15.1")
    # a novel gene absent from the training vocabulary -> OOV, not an error
    row, oov = build_feature_row(_vector(gene_presence={"blaNDM-5": True}), schema)
    assert oov == 1
    assert row.shape[0] == len(schema.feature_names)


def test_assemble_feature_matrix_shape_and_index() -> None:
    v1 = _vector(genome_id="g1", gene_presence={"blaKPC-2": True})
    v2 = _vector(genome_id="g2", gene_presence={"sul1": True})
    schema = build_vocabulary([v1, v2], amrfinder_db_version="2026-05-15.1")
    matrix = assemble_feature_matrix([v1, v2], schema)
    assert list(matrix.index) == ["g1", "g2"]
    assert list(matrix.columns) == list(schema.feature_names)
    assert matrix.loc["g1", "blaKPC-2"] == 1.0
    assert matrix.loc["g2", "sul1"] == 1.0
