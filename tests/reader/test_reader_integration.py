"""End-to-end Reader integration test -- EPIC 2's mandatory per-user-story test, shape
#2 from Documentation/08-crosscutting-concepts/README.md: "FASTA fixture -> MockAnnotator
-> feature vector (matches feature_schema.json)". No Docker/AMRFinderPlus (golden rule #6).
"""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

from genome_firewall.annotation.mock import MockAnnotator
from genome_firewall.reader.fasta_parser import FastaParseError, parse_fasta
from genome_firewall.reader.feature_builder import (
    ReferenceGeneCatalog,
    build_feature_vector,
    write_feature_schema,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_FASTA_FIXTURE = _REPO_ROOT / "tests" / "fixtures" / "reader" / "573.10001.fna"
_AMRFINDER_FIXTURE_DIR = _REPO_ROOT / "tests" / "fixtures" / "amrfinder"
_CATALOG_PATH = _REPO_ROOT / "data" / "reference" / "ReferenceGeneCatalog.txt"
_FEATURE_SCHEMA_PATH = _REPO_ROOT / "src" / "genome_firewall" / "reader" / "feature_schema.json"


@pytest.mark.integration
def test_fasta_to_feature_vector_via_mock_annotator() -> None:
    """The full reader pipeline, one hop at a time: parse -> annotate -> build features."""
    genome_input = parse_fasta(_FASTA_FIXTURE, genome_id="573.10001")
    assert genome_input.genome_id == "573.10001"

    annotator = MockAnnotator(_AMRFINDER_FIXTURE_DIR)
    annotation = annotator.annotate(_FASTA_FIXTURE, genome_id=genome_input.genome_id)
    assert annotation.ok is True
    assert annotation.data is not None

    catalog = ReferenceGeneCatalog(_CATALOG_PATH)
    vector = build_feature_vector(
        genome_input.genome_id,
        annotation.data,
        amrfinder_db_version=annotation.amrfinder_db_version or "unknown",
        catalog=catalog,
    )

    assert vector.gene_presence["blaSHV-11"] is True
    assert vector.point_mutations["gyrA_S83Y"] is True
    assert vector.gene_hit_count["blaTEM-1"] == 2


@pytest.mark.integration
def test_clean_genome_produces_empty_but_well_formed_vector() -> None:
    """A genome with zero AMR/stress/virulence calls must not crash the pipeline."""
    genome_input = parse_fasta(_FASTA_FIXTURE, genome_id="573.10002")
    annotator = MockAnnotator(_AMRFINDER_FIXTURE_DIR)
    annotation = annotator.annotate(_FASTA_FIXTURE, genome_id=genome_input.genome_id)
    assert annotation.ok is True
    assert annotation.data == ()

    vector = build_feature_vector(
        genome_input.genome_id,
        annotation.data,
        amrfinder_db_version=annotation.amrfinder_db_version or "unknown",
    )
    assert vector.gene_presence == {}
    assert vector.point_mutations == {}


@pytest.mark.integration
def test_committed_feature_schema_matches_what_the_current_code_generates(tmp_path: Path) -> None:
    """Guards against the committed src/.../feature_schema.json drifting from what
    write_feature_schema would produce right now -- a weaker check (just comparing
    top-level property names) would miss a changed field TYPE, not just a changed set.
    """
    regenerated_path = tmp_path / "feature_schema.json"
    committed = json.loads(_FEATURE_SCHEMA_PATH.read_text(encoding="utf-8"))
    write_feature_schema(regenerated_path, amrfinder_db_version=committed["amrfinder_db_version"])
    regenerated = json.loads(regenerated_path.read_text(encoding="utf-8"))
    assert regenerated == committed, (
        "src/genome_firewall/reader/feature_schema.json is stale -- regenerate it via "
        "write_feature_schema() after any GenomeFeatureVector change"
    )


@pytest.mark.integration
def test_malformed_fasta_fails_at_parse_stage_not_downstream() -> None:
    """A bad upload must be rejected before it ever reaches annotation/feature-building."""
    with pytest.raises(FastaParseError):
        parse_fasta(io.StringIO("this is not a fasta file\n"), genome_id="573.10001")
