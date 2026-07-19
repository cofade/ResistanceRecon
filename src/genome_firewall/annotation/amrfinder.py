"""AMRFinderPlus Docker/WSL2 runner (issue #16).

The ONLY place a subprocess/Docker call happens in this pipeline (golden rule #6).
Never imported/run in CI -- MockAnnotator (mock.py) stands in for every non-live test.
"""

from __future__ import annotations

import csv
import re
import subprocess
from pathlib import Path

from pydantic import ValidationError

from genome_firewall.annotation._tsv import parse_amrfinder_tsv
from genome_firewall.schemas import AnnotationResult

#: genome_id flows into a filename (output_path) and Docker's --name; keep it to a safe,
#: unambiguous charset so it can never be interpreted as a path segment (e.g. "..").
_SAFE_GENOME_ID = re.compile(r"^[A-Za-z0-9._-]+$")

#: Pinned per ADR-0002 -- fixes both the amrfinder binary and its database build so a run
#: today and a run in a year use the identical reference data. Confirmed against a live
#: pull: `docker pull ncbi/amr:4.2.7-2026-05-15.1` resolves to software 4.2.7 / DB 2026-05-15.1.
DEFAULT_IMAGE_TAG = "ncbi/amr:4.2.7-2026-05-15.1"
PINNED_DB_VERSION = "2026-05-15.1"

#: amrfinder prints "Database version: X" to STDERR during the run, not stdout -- confirmed
#: against a live run; do not move this search to stdout.
_DB_VERSION_RE = re.compile(r"Database version:\s*(\S+)")


def run_amrfinder(
    fasta_path: Path,
    *,
    genome_id: str,
    image_tag: str = DEFAULT_IMAGE_TAG,
    organism: str = "Klebsiella_pneumoniae",
    threads: int = 4,
    timeout: float = 600.0,
) -> AnnotationResult:
    """Run AMRFinderPlus via Docker against one genome FASTA and return its AMR calls.

    `fasta_path`'s parent directory is bind-mounted read/write at /data inside the
    container so amrfinder can read the input and write its output TSV there. Never
    raises past the envelope -- Docker-not-found, a non-zero exit, and a timeout all
    become `ok=False` with a hinted error message.
    """
    source = f"docker:{image_tag}"
    if not _SAFE_GENOME_ID.match(genome_id):
        return AnnotationResult(
            ok=False,
            source=source,
            error=f"invalid genome_id {genome_id!r}: must match {_SAFE_GENOME_ID.pattern}",
        )
    data_dir = fasta_path.resolve().parent
    output_path = data_dir / f"{genome_id}.amrfinder.tsv"
    command = [
        "docker",
        "run",
        "--rm",
        "-v",
        f"{data_dir}:/data",
        image_tag,
        "amrfinder",
        "-n",
        f"/data/{fasta_path.name}",
        "-O",
        organism,
        "--plus",
        "--threads",
        str(threads),
        "--name",
        genome_id,
        "-o",
        f"/data/{output_path.name}",
    ]

    try:
        # Fixed argv list, no shell=True, no untrusted input -- see bandit's B603/B607.
        result = subprocess.run(
            command, capture_output=True, text=True, timeout=timeout, check=False
        )
    except FileNotFoundError:
        return AnnotationResult(
            ok=False,
            source=source,
            error="docker executable not found -- is Docker Desktop/WSL2 installed and on PATH?",
        )
    except subprocess.TimeoutExpired:
        return AnnotationResult(
            ok=False,
            source=source,
            error=f"amrfinder did not complete within {timeout}s (Docker/WSL2 may be unresponsive)",
        )

    if result.returncode != 0:
        return AnnotationResult(
            ok=False,
            source=source,
            error=f"amrfinder exited {result.returncode}: {result.stderr.strip()[-2000:]}",
        )
    if not output_path.exists():
        return AnnotationResult(
            ok=False,
            source=source,
            error=f"amrfinder reported success but did not write {output_path}",
        )

    db_version_match = _DB_VERSION_RE.search(result.stderr)
    db_version = db_version_match.group(1) if db_version_match else None
    try:
        features = parse_amrfinder_tsv(output_path)
    except (ValidationError, csv.Error, OSError, KeyError, ValueError) as exc:
        return AnnotationResult(
            ok=False,
            source=source,
            error=(
                f"amrfinder ran but its output did not match the expected shape (possible "
                f"AMRFinderPlus DB-version drift): {exc}"
            ),
        )
    return AnnotationResult(ok=True, source=source, data=features, amrfinder_db_version=db_version)
