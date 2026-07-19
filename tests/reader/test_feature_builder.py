"""Unit tests for reader.feature_builder (issue #17)."""

from __future__ import annotations

import json
from pathlib import Path

from genome_firewall.annotation._tsv import parse_amrfinder_tsv
from genome_firewall.reader.feature_builder import (
    SCHEMA_VERSION,
    ReferenceGeneCatalog,
    build_feature_vector,
    write_feature_schema,
)

_AMRFINDER_FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "amrfinder"
_CATALOG_PATH = (
    Path(__file__).resolve().parents[2] / "data" / "reference" / "ReferenceGeneCatalog.txt"
)
_DB_VERSION = "2026-05-15.1"


def _vector_for(genome_id: str, *, catalog: ReferenceGeneCatalog | None = None):
    features = parse_amrfinder_tsv(_AMRFINDER_FIXTURE_DIR / f"{genome_id}.tsv")
    return build_feature_vector(
        genome_id, features, amrfinder_db_version=_DB_VERSION, catalog=catalog
    )


def test_pivots_gene_presence_and_point_mutations() -> None:
    vector = _vector_for("573.10001")

    assert vector.gene_presence["blaSHV-11"] is True
    assert vector.gene_presence["blaOXA"] is True
    assert "ompK35_K292QfsTer17" not in vector.gene_presence  # POINT_DISRUPT, not presence/absence

    assert vector.point_mutations["gyrA_S83Y"] is True
    assert vector.point_mutations["ompK35_K292QfsTer17"] is True
    assert vector.point_mutation_disrupt["ompK35_K292QfsTer17"] is True
    assert "gyrA_S83Y" not in vector.point_mutation_disrupt


def test_stress_scope_genes_excluded_from_both_tables() -> None:
    vector = _vector_for("573.10001")
    assert "fieF" not in vector.gene_presence
    assert "pcoS" not in vector.gene_presence


def test_near_duplicate_hits_are_counted_not_collapsed() -> None:
    vector = _vector_for("573.10001")
    assert vector.gene_hit_count["blaTEM-1"] == 2
    assert vector.gene_hit_count["blaSHV-11"] == 1


def test_partial_contig_end_flagged_separately() -> None:
    vector = _vector_for("573.10003")
    assert vector.partial_contig_end_genes == ("blaKPC-3",)
    assert vector.gene_presence["blaKPC-3"] is True


def test_empty_genome_yields_empty_tables() -> None:
    vector = _vector_for("573.10002")
    assert vector.gene_presence == {}
    assert vector.point_mutations == {}


def test_unmapped_class_flagged_without_catalog() -> None:
    vector = _vector_for("573.10003")
    assert "newGene-1" in vector.unmapped_class_genes
    assert "ydgH-like" in vector.unmapped_class_genes
    assert "newGene-1" not in vector.gene_drug_class
    assert "ydgH-like" not in vector.gene_drug_class


def test_catalog_resolves_a_blank_class_gene_and_stores_it() -> None:
    """blaSHV-12's real Class/Subclass is blanked in the fixture TSV to simulate a gap
    the TSV itself left -- ReferenceGeneCatalog must fill it, and it must not end up in
    unmapped_class_genes once resolved (this is the behavior ADR-0013 exists for).
    """
    catalog = ReferenceGeneCatalog(_CATALOG_PATH)
    vector = _vector_for("573.10003", catalog=catalog)

    assert vector.gene_drug_class["blaSHV-12"] == "BETA-LACTAM"
    assert vector.gene_drug_subclass["blaSHV-12"] == "CEFIDEROCOL/CEPHALOSPORIN"
    assert "blaSHV-12" not in vector.unmapped_class_genes


def test_catalog_fills_a_blank_subclass_when_class_is_already_known() -> None:
    """The catalog fallback must fire per-column, not only when the whole pair is blank."""
    catalog = ReferenceGeneCatalog(_CATALOG_PATH)
    vector = _vector_for("573.10003", catalog=catalog)

    assert vector.gene_drug_class["blaTEM-1"] == "BETA-LACTAM"  # from the TSV directly
    assert vector.gene_drug_subclass["blaTEM-1"] == "BETA-LACTAM"  # backfilled by the catalog


def test_catalog_does_not_invent_a_class_for_a_gene_it_does_not_know() -> None:
    catalog = ReferenceGeneCatalog(_CATALOG_PATH)
    vector = _vector_for("573.10003", catalog=catalog)

    assert "newGene-1" in vector.unmapped_class_genes
    assert "newGene-1" not in vector.gene_drug_class


def test_tsv_supplied_class_is_stored_without_needing_a_catalog() -> None:
    vector = _vector_for("573.10001")
    assert vector.gene_drug_class["blaSHV-11"] == "BETA-LACTAM"
    assert vector.gene_drug_subclass["blaSHV-11"] == "BETA-LACTAM"


def test_reference_gene_catalog_resolves_class_by_allele() -> None:
    catalog = ReferenceGeneCatalog(_CATALOG_PATH)
    resolved = catalog.lookup("blaTEM-1")
    assert resolved == ("BETA-LACTAM", "BETA-LACTAM")


def test_reference_gene_catalog_returns_none_for_unknown_gene() -> None:
    catalog = ReferenceGeneCatalog(_CATALOG_PATH)
    assert catalog.lookup("totally-made-up-gene-xyz") is None


def test_write_feature_schema(tmp_path: Path) -> None:
    output_path = tmp_path / "feature_schema.json"
    write_feature_schema(output_path, amrfinder_db_version="2026-05-15.1")
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == SCHEMA_VERSION
    assert payload["amrfinder_db_version"] == "2026-05-15.1"
    assert "genome_feature_vector_json_schema" in payload
