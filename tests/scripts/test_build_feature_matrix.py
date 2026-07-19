"""Offline test for the batch feature-matrix builder (issue #18): the MockAnnotator path
proves the reader -> features pipeline end-to-end without Docker (golden rule #6)."""

from __future__ import annotations

from pathlib import Path

import build_feature_matrix as bfm

from genome_firewall.annotation.mock import MockAnnotator
from genome_firewall.reader.feature_builder import ReferenceGeneCatalog

_REPO_ROOT = Path(__file__).resolve().parents[2]
_FIXTURE_DIR = _REPO_ROOT / "tests" / "fixtures" / "amrfinder"
_CATALOG = _REPO_ROOT / "data" / "reference" / "ReferenceGeneCatalog.txt"


def test_build_genome_vectors_and_matrix_via_mock(tmp_path: Path) -> None:
    annotator = MockAnnotator(_FIXTURE_DIR)
    catalog = ReferenceGeneCatalog(_CATALOG)
    # MockAnnotator selects the fixture purely by genome_id; the FASTA path is never read.
    fasta_paths = {"573.10001": tmp_path / "573.10001.fna"}
    cache_dir = tmp_path / "cache"

    vectors, failures = bfm.build_genome_vectors(
        fasta_paths, annotator, catalog, cache_dir=cache_dir
    )
    assert not failures
    assert len(vectors) == 1
    assert (cache_dir / "573.10001.json").exists()  # cached for resumability

    matrix, schema = bfm.build_feature_matrix(vectors)
    assert matrix.shape[0] == 1
    assert list(matrix.columns) == list(schema.feature_names)
    assert len(schema.feature_names) >= 1

    # a second call is served from cache (idempotent/resumable)
    vectors_again, failures_again = bfm.build_genome_vectors(
        fasta_paths, annotator, catalog, cache_dir=cache_dir
    )
    assert not failures_again
    assert vectors_again[0].genome_id == "573.10001"


def test_build_genome_vectors_records_failures(tmp_path: Path) -> None:
    annotator = MockAnnotator(_FIXTURE_DIR)
    catalog = ReferenceGeneCatalog(_CATALOG)
    vectors, failures = bfm.build_genome_vectors(
        {"does-not-exist": tmp_path / "x.fna"}, annotator, catalog
    )
    assert vectors == []
    assert len(failures) == 1 and "does-not-exist" in failures[0]
