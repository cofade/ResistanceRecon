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
    """Uses ftps_download_flatfile (issue #41) to tolerate BV-BRC's server-side
    singular/plural filename drift instead of pinning one name.

    A 425 (router-ALG data-channel block, §11.4) is a documented network constraint
    on some networks, not a code defect, and it can only happen *after* a name
    resolved past the control-channel 550 check -- so it's skipped, not failed. If
    every known name still 550s, the server has drifted to a name this list doesn't
    know about yet and the test fails loudly on purpose.
    """
    result = fetch_bvbrc_data.ftps_download_flatfile(
        fetch_bvbrc_data.DEFAULT_HOST, tmp_path, timeout=30.0
    )
    if (
        not result.ok
        and result.error
        and ("425" in result.error or "data connection" in result.error.lower())
    ):
        pytest.skip(f"FTPS data channel blocked on this network (§11.4): {result.error}")
    assert result.ok, result.error
    assert result.path is not None
    assert result.path.exists()
    assert result.path.stat().st_size > 0


@pytest.mark.live
def test_solr_evidence_facet_has_lab_method() -> None:
    payload = fetch_bvbrc_data.solr_facet(
        "genome_amr", fetch_bvbrc_data.evidence_vocabulary_rql(573), timeout=30.0
    )
    # json(nl,map) makes Solr return the facet as {value: count, ...}, not a flat list.
    facet = payload.get("facet_counts", {}).get("facet_fields", {}).get("evidence", {})
    assert "Laboratory Method" in facet
    assert facet["Laboratory Method"] > 0


@pytest.mark.live
def test_solr_numfound_nonzero() -> None:
    payload = fetch_bvbrc_data.solr_facet(
        "genome_amr", fetch_bvbrc_data.lab_ast_facet_rql(573), timeout=30.0
    )
    assert payload.get("response", {}).get("numFound", 0) > 0
