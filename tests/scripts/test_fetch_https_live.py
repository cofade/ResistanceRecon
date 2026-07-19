"""Live validation of the HTTPS BV-BRC Data API path (ADR-0016) -- the non-FTPS route the
real run relies on. Skipped unless GF_RUN_LIVE=1 (the FTPS `425` pitfall in §11.4 is exactly
the class of failure only a live test catches). Self-discovers a real K. pneumoniae genome so
no genome_id is hard-coded."""

from __future__ import annotations

from pathlib import Path

import fetch_bvbrc_data as fetch
import pytest

from genome_firewall.constants import KLEBSIELLA_PNEUMONIAE_TAXON_ID

pytestmark = pytest.mark.live

_LAB_FILTER = (
    f"and(eq(taxon_id,{KLEBSIELLA_PNEUMONIAE_TAXON_ID}),"
    f"eq(evidence,{fetch._rql_value(fetch.LAB_EVIDENCE)}))"
)


def _one_kp_genome_id() -> str:
    records = fetch.solr_select_records(
        "genome_amr",
        f"{_LAB_FILTER}&select(genome_id)",
        page_size=5,
        max_records=5,
    )
    assert records, "no lab-AST genome_amr records returned from the HTTPS Data API"
    return str(records[0]["genome_id"])


def test_https_labels_select_returns_lab_ast_rows() -> None:
    records = fetch.solr_select_records(
        "genome_amr",
        f"{_LAB_FILTER}&select(genome_id,antibiotic,resistant_phenotype,evidence)",
        page_size=10,
        max_records=10,
    )
    assert len(records) == 10
    assert records[0]["evidence"] == fetch.LAB_EVIDENCE
    assert "antibiotic" in records[0]


def test_https_fasta_download_passes_the_sanity_check(tmp_path: Path) -> None:
    genome_id = _one_kp_genome_id()
    dest = tmp_path / f"{genome_id}.fna"
    result = fetch.https_fasta_download(genome_id, dest)
    assert result.ok, result.error
    assert dest.exists() and dest.stat().st_size > 0
    text = dest.read_text(encoding="utf-8")
    assert fetch._fasta_contig_count(text) >= 1
    assert fetch._fasta_total_length(text) > 1000
