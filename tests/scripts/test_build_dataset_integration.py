"""End-to-end integration test for the EPIC 1 data-pipeline shape (Documentation/08-
crosscutting-concepts/README.md's Integration-test mandate, shape #1): fixture data ->
normalized labels -> persisted dataset contract.

Drives the real scripts/build_dataset.py orchestration (not just the individual pure
functions unit-tested in tests/predictor/test_dataset.py) against the committed BV-BRC
fixtures, through the actual parquet/JSON boundary a consumer would read.
"""

from __future__ import annotations

from pathlib import Path

import build_dataset
import pandas as pd
import pytest

from genome_firewall.predictor import dataset

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "bvbrc"


@pytest.mark.integration
def test_build_dataset_end_to_end(tmp_path: Path) -> None:
    """fixture flat file + metadata + FASTA dir -> build() -> the four persisted
    outputs, each readable back through the real contract (dataset.LABELS_COLUMNS,
    dataset.validate_labels_schema, and the DatasetManifest shape)."""
    out_dir = tmp_path / "processed"

    manifest = build_dataset.build(
        flatfile=FIXTURES_DIR / "patric_genome_amr_sample.tsv",
        out_dir=out_dir,
        metadata=FIXTURES_DIR / "genome_metadata_sample.tsv",
        fasta_dir=FIXTURES_DIR / "genomes",
    )

    labels_path = out_dir / "labels.parquet"
    ast_rows_path = out_dir / "ast_lab_rows.parquet"
    genome_metadata_path = out_dir / "genome_metadata.parquet"
    manifest_path = out_dir / "dataset_manifest.json"
    for path in (labels_path, ast_rows_path, genome_metadata_path, manifest_path):
        assert path.exists(), f"missing persisted output: {path}"

    labels = pd.read_parquet(labels_path)
    dataset.validate_labels_schema(labels)  # the persisted contract, not just in-memory
    assert len(labels) == manifest.counts.labels_after_collapse
    assert bool(labels.loc[labels["genome_id"] == "573.10001", "has_fasta"].iat[0]) is True

    ast_rows = pd.read_parquet(ast_rows_path)
    assert len(ast_rows) == manifest.counts.lab_rows

    genome_metadata = pd.read_parquet(genome_metadata_path)
    assert len(genome_metadata) == manifest.mlst.genomes_total

    # The manifest round-trips through the real JSON file a downstream consumer reads.
    reloaded = dataset.DatasetManifest.model_validate_json(
        manifest_path.read_text(encoding="utf-8")
    )
    assert reloaded.counts.raw_rows == manifest.counts.raw_rows == 22
    assert reloaded.evidence_vocabulary["Laboratory Method"] == 20
