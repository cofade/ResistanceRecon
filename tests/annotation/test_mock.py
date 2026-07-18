"""Unit tests for annotation.mock.MockAnnotator (issue #16)."""

from __future__ import annotations

from pathlib import Path

from genome_firewall.annotation.amrfinder import PINNED_DB_VERSION
from genome_firewall.annotation.mock import MockAnnotator

_FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "amrfinder"
_IRRELEVANT_FASTA_PATH = Path("unused.fna")


def test_annotate_returns_ok_envelope_for_known_genome() -> None:
    result = MockAnnotator(_FIXTURE_DIR).annotate(_IRRELEVANT_FASTA_PATH, genome_id="573.10001")
    assert result.ok is True
    assert result.error is None
    assert result.data is not None
    assert len(result.data) == 9
    assert result.amrfinder_db_version == PINNED_DB_VERSION


def test_annotate_returns_empty_data_for_clean_genome() -> None:
    result = MockAnnotator(_FIXTURE_DIR).annotate(_IRRELEVANT_FASTA_PATH, genome_id="573.10002")
    assert result.ok is True
    assert result.data == ()


def test_annotate_fails_closed_for_unknown_genome_id() -> None:
    annotator = MockAnnotator(_FIXTURE_DIR)
    result = annotator.annotate(_IRRELEVANT_FASTA_PATH, genome_id="no-such-genome")
    assert result.ok is False
    assert result.data is None
    assert result.error is not None
    assert "no-such-genome" in result.error


def test_annotate_fails_closed_for_a_malformed_fixture(tmp_path: Path) -> None:
    header = (
        "Name\tProtein id\tContig id\tStart\tStop\tStrand\tElement symbol\tElement name\t"
        "Scope\tType\tSubtype\tClass\tSubclass\tMethod\tTarget length\t"
        "Reference sequence length\t% Coverage of reference\t% Identity to reference\t"
        "Alignment length\tClosest reference accession\tClosest reference name\t"
        "HMM accession\tHMM description\n"
    )
    bad_row = (
        "bad\tNA\tc1\t1\t10\t+\tg\tg\tcore\tAMR\tAMR\tX\tX\tNOT_A_REAL_METHOD\t10\t10\t"
        "100.00\t100.00\t10\tNA\tNA\tNA\tNA\n"
    )
    (tmp_path / "bad-fixture.tsv").write_text(header + bad_row, encoding="utf-8")

    result = MockAnnotator(tmp_path).annotate(_IRRELEVANT_FASTA_PATH, genome_id="bad-fixture")
    assert result.ok is False
    assert result.data is None
    assert result.error is not None and "did not match the expected shape" in result.error
