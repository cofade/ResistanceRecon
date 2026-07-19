"""Offline tests for the HTTPS Data API fetch helpers (ADR-0016) -- the pure pieces of
scripts/fetch_bvbrc_data.py's non-FTPS path, especially the truncation guard (§11.4)."""

from __future__ import annotations

from pathlib import Path

import fetch_bvbrc_data as fetch
import pandas as pd


def test_fasta_contig_count_and_length() -> None:
    text = ">c1\nACGT\nACGT\n>c2\nAC\n"
    assert fetch._fasta_contig_count(text) == 2
    assert fetch._fasta_total_length(text) == 10  # 4 + 4 + 2


def test_fasta_sanity_problem_accepts_a_matching_genome() -> None:
    assert (
        fetch.fasta_sanity_problem(150, 5_000_000, expected_contigs=150, expected_length=5_000_000)
        is None
    )


def test_fasta_sanity_problem_flags_contig_count_mismatch() -> None:
    problem = fetch.fasta_sanity_problem(25, 100_000, expected_contigs=200)
    assert problem is not None and "contig count" in problem


def test_fasta_sanity_problem_flags_the_limit_ceiling() -> None:
    problem = fetch.fasta_sanity_problem(25_000, 5_000_000, limit_ceiling=25_000)
    assert problem is not None and "truncat" in problem.lower()


def test_fasta_sanity_problem_flags_empty_and_length_drift() -> None:
    assert fetch.fasta_sanity_problem(0, 0) is not None
    drift = fetch.fasta_sanity_problem(150, 4_000_000, expected_length=5_000_000)
    assert drift is not None and "length" in drift


def test_write_tsv_fills_missing_columns(tmp_path: Path) -> None:
    dest = tmp_path / "amr.tsv"
    fetch._write_tsv(
        [{"genome_id": "g1", "antibiotic": "meropenem"}],
        ("genome_id", "antibiotic", "evidence"),
        dest,
    )
    frame = pd.read_csv(dest, sep="\t", dtype=str, keep_default_na=False)
    assert list(frame.columns) == ["genome_id", "antibiotic", "evidence"]
    assert frame.loc[0, "evidence"] == ""
