"""Unit tests for annotation.amrfinder.run_amrfinder (issue #16) -- exercises the
envelope's failure paths without needing a real Docker daemon. `subprocess.run` is
monkeypatched at the module level; the real Docker invocation is validated manually
(see the PR description for the live-run log), per golden rule #6 (never Docker in CI).
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from genome_firewall.annotation.amrfinder import run_amrfinder


def test_docker_not_found(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fasta_path = tmp_path / "genome.fna"
    fasta_path.write_text(">contig_1\nACGT\n", encoding="utf-8")

    def _raise_not_found(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        raise FileNotFoundError

    monkeypatch.setattr(subprocess, "run", _raise_not_found)
    result = run_amrfinder(fasta_path, genome_id="g1")
    assert result.ok is False
    assert result.data is None
    assert result.error is not None and "docker executable not found" in result.error


def test_timeout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fasta_path = tmp_path / "genome.fna"
    fasta_path.write_text(">contig_1\nACGT\n", encoding="utf-8")

    def _raise_timeout(*_args: object, **kwargs: object) -> subprocess.CompletedProcess[str]:
        raise subprocess.TimeoutExpired(cmd="amrfinder", timeout=kwargs.get("timeout", 0))  # type: ignore[arg-type]

    monkeypatch.setattr(subprocess, "run", _raise_timeout)
    result = run_amrfinder(fasta_path, genome_id="g1", timeout=1.0)
    assert result.ok is False
    assert result.error is not None and "did not complete within" in result.error


def test_nonzero_exit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fasta_path = tmp_path / "genome.fna"
    fasta_path.write_text(">contig_1\nACGT\n", encoding="utf-8")

    def _fake_run(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr="boom")

    monkeypatch.setattr(subprocess, "run", _fake_run)
    result = run_amrfinder(fasta_path, genome_id="g1")
    assert result.ok is False
    assert result.error is not None
    assert "amrfinder exited 1" in result.error
    assert "boom" in result.error


def test_success_writes_and_parses_output(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fasta_path = tmp_path / "genome.fna"
    fasta_path.write_text(">contig_1\nACGT\n", encoding="utf-8")
    output_path = tmp_path / "g1.amrfinder.tsv"
    header = (
        "Name\tProtein id\tContig id\tStart\tStop\tStrand\tElement symbol\tElement name\t"
        "Scope\tType\tSubtype\tClass\tSubclass\tMethod\tTarget length\t"
        "Reference sequence length\t% Coverage of reference\t% Identity to reference\t"
        "Alignment length\tClosest reference accession\tClosest reference name\t"
        "HMM accession\tHMM description\n"
    )
    row = (
        "g1\tNA\tcontig_1\t1\t100\t+\tblaTEM-1\tTEM-1 beta-lactamase\tcore\tAMR\tAMR\t"
        "BETA-LACTAM\tBETA-LACTAM\tALLELEX\t100\t100\t100.00\t100.00\t100\t"
        "WP_000027057.1\tTEM-1\tNA\tNA\n"
    )

    def _fake_run(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        output_path.write_text(header + row, encoding="utf-8")
        stderr = "Database version: 2026-05-15.1\namrfinder took 1 seconds to complete\n"
        return subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr=stderr)

    monkeypatch.setattr(subprocess, "run", _fake_run)
    result = run_amrfinder(fasta_path, genome_id="g1")
    assert result.ok is True
    assert result.amrfinder_db_version == "2026-05-15.1"
    assert result.data is not None
    assert len(result.data) == 1
    assert result.data[0].gene_symbol == "blaTEM-1"


def test_rejects_unsafe_genome_id(tmp_path: Path) -> None:
    fasta_path = tmp_path / "genome.fna"
    fasta_path.write_text(">contig_1\nACGT\n", encoding="utf-8")

    result = run_amrfinder(fasta_path, genome_id="../../etc/passwd")
    assert result.ok is False
    assert result.error is not None and "invalid genome_id" in result.error


def test_malformed_output_is_caught_into_the_envelope_not_raised(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A Method value outside AmrMethod's closed Literal set (e.g. a future AMRFinderPlus
    DB adding a new value) must fail closed via the envelope, not raise past it -- this is
    exactly the DB-version-drift scenario golden rule #6's isolation exists to contain.
    """
    fasta_path = tmp_path / "genome.fna"
    fasta_path.write_text(">contig_1\nACGT\n", encoding="utf-8")
    output_path = tmp_path / "g1.amrfinder.tsv"
    header = (
        "Name\tProtein id\tContig id\tStart\tStop\tStrand\tElement symbol\tElement name\t"
        "Scope\tType\tSubtype\tClass\tSubclass\tMethod\tTarget length\t"
        "Reference sequence length\t% Coverage of reference\t% Identity to reference\t"
        "Alignment length\tClosest reference accession\tClosest reference name\t"
        "HMM accession\tHMM description\n"
    )
    row = (
        "g1\tNA\tcontig_1\t1\t100\t+\tsomeGene\tsome gene\tcore\tAMR\tAMR\t"
        "BETA-LACTAM\tBETA-LACTAM\tNOT_A_REAL_METHOD\t100\t100\t100.00\t100.00\t100\t"
        "WP_000000000.1\tsome gene\tNA\tNA\n"
    )

    def _fake_run(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        output_path.write_text(header + row, encoding="utf-8")
        return subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", _fake_run)
    result = run_amrfinder(fasta_path, genome_id="g1")
    assert result.ok is False
    assert result.data is None
    assert result.error is not None and "DB-version drift" in result.error


def test_success_but_missing_output_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fasta_path = tmp_path / "genome.fna"
    fasta_path.write_text(">contig_1\nACGT\n", encoding="utf-8")

    def _fake_run(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")

    monkeypatch.setattr(subprocess, "run", _fake_run)
    result = run_amrfinder(fasta_path, genome_id="g1")
    assert result.ok is False
    assert result.error is not None and "did not write" in result.error
