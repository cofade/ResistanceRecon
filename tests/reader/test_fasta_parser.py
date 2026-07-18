"""Unit tests for reader.fasta_parser (issue #15)."""

from __future__ import annotations

import io

import pytest

from genome_firewall.reader import fasta_parser
from genome_firewall.reader.fasta_parser import FastaParseError, parse_fasta

_VALID_FASTA = (
    ">contig_1 test contig one\n"
    + "ACGT" * 30_000
    + "\n>contig_2 test contig two\n"
    + "ACGTN" * 10_000
    + "\n"
)


def test_parses_valid_multi_contig_fasta() -> None:
    genome = parse_fasta(io.StringIO(_VALID_FASTA), genome_id="test.1")
    assert genome.genome_id == "test.1"
    assert genome.species == "Klebsiella pneumoniae"
    assert [c.contig_id for c in genome.contigs] == ["contig_1", "contig_2"]
    assert genome.contigs[0].length == 120_000
    assert genome.contigs[1].length == 50_000


def test_rejects_empty_content() -> None:
    with pytest.raises(FastaParseError, match="no FASTA records"):
        parse_fasta(io.StringIO(""), genome_id="test.1")


def test_rejects_non_fasta_content() -> None:
    # Biopython's strict 'fasta' parser raises on leading non-'>' content rather than
    # silently yielding zero records -- both paths land in FastaParseError.
    with pytest.raises(FastaParseError, match="could not read FASTA content"):
        parse_fasta(io.StringIO("this is not a fasta file\njust text\n"), genome_id="test.1")


def test_rejects_duplicate_contig_ids() -> None:
    content = ">dup\n" + "ACGT" * 30_000 + "\n>dup\n" + "ACGT" * 30_000 + "\n"
    with pytest.raises(FastaParseError, match="duplicate contig id"):
        parse_fasta(io.StringIO(content), genome_id="test.1")


def test_rejects_protein_like_characters() -> None:
    # E/F/I/L/P/Q/X/Z are amino-acid-only letters -- not valid IUPAC nucleotide codes.
    content = ">contig_1\n" + "MEFILPQXZ" * 5_000 + "\n"
    with pytest.raises(FastaParseError, match="non-nucleotide characters"):
        parse_fasta(io.StringIO(content), genome_id="test.1")


def test_rejects_all_ambiguous_contig() -> None:
    content = ">contig_1\n" + "N" * 100_000 + "\n"
    with pytest.raises(FastaParseError, match="no canonical A/C/G/T bases"):
        parse_fasta(io.StringIO(content), genome_id="test.1")


def test_rejects_missing_contig_id() -> None:
    content = ">\n" + "ACGT" * 30_000 + "\n"
    with pytest.raises(FastaParseError, match="missing an id"):
        parse_fasta(io.StringIO(content), genome_id="test.1")


def test_rejects_total_length_below_minimum() -> None:
    content = ">contig_1\n" + "ACGT" * 12_500 + "\n"  # 50,000bp, below the 100,000bp floor
    with pytest.raises(FastaParseError, match="outside the sane range"):
        parse_fasta(io.StringIO(content), genome_id="test.1")


def test_rejects_too_many_contigs(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(fasta_parser, "_MAX_CONTIGS", 2)
    content = "".join(f">contig_{i}\nACGTACGTACGT\n" for i in range(3))
    with pytest.raises(FastaParseError, match="exceeds the sane maximum"):
        parse_fasta(io.StringIO(content), genome_id="test.1")
