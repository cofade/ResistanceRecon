"""Live network tests against the real BV-BRC FTPS/Solr endpoints.

Skipped by default (see tests/conftest.py's pytest_collection_modifyitems) -- opt in
with ``GF_RUN_LIVE=1 uv run pytest -m live``. These are the only tests in this
project allowed to touch the network; everything else (including
tests/predictor/test_dataset.py) runs against committed fixtures under the autouse
``_no_network`` guard.
"""

from __future__ import annotations

from pathlib import Path

import fetch_bvbrc_data
import pytest


@pytest.mark.live
def test_ftps_flatfile_header_downloads(tmp_path: Path) -> None:
    dest = tmp_path / "PATRIC_genome_AMR.txt"
    result = fetch_bvbrc_data.ftps_download(
        fetch_bvbrc_data.DEFAULT_HOST,
        f"{fetch_bvbrc_data.RELEASE_NOTES_DIR}/{fetch_bvbrc_data.DEFAULT_FLATFILE}",
        dest,
        timeout=30.0,
    )
    assert result.ok, result.error
    assert dest.exists()
    assert dest.stat().st_size > 0


@pytest.mark.live
def test_solr_evidence_facet_has_lab_method() -> None:
    payload = fetch_bvbrc_data.solr_facet(
        "genome_amr", fetch_bvbrc_data.evidence_vocabulary_rql(573), timeout=30.0
    )
    facets = payload.get("facet_counts", {}).get("facet_fields", {}).get("evidence", [])
    values = facets[::2]  # Solr facet_fields is a flat [value, count, value, count, ...] list
    assert "Laboratory Method" in values


@pytest.mark.live
def test_solr_numfound_nonzero() -> None:
    payload = fetch_bvbrc_data.solr_facet(
        "genome_amr", fetch_bvbrc_data.lab_ast_facet_rql(573), timeout=30.0
    )
    assert payload.get("response", {}).get("numFound", 0) > 0
