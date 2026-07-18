"""MockAnnotator (issue #16) -- reads committed fixture TSVs instead of running Docker
(golden rule #6: AMRFinderPlus never runs in CI). This is what CI and every non-live
test use exclusively.

Uses the exact same TSV parser as the real runner (annotation.amrfinder), so mock and
real output are structurally identical by construction, not by discipline.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import ValidationError

from genome_firewall.annotation._tsv import parse_amrfinder_tsv
from genome_firewall.annotation.amrfinder import PINNED_DB_VERSION
from genome_firewall.schemas import AnnotationResult


class MockAnnotator:
    """A drop-in stand-in for `annotation.amrfinder.run_amrfinder`, backed by fixture TSVs.

    Every fixture file is named `<genome_id>.tsv` under `fixture_dir`.
    """

    def __init__(self, fixture_dir: Path) -> None:
        self._fixture_dir = fixture_dir

    def annotate(self, fasta_path: Path, *, genome_id: str) -> AnnotationResult:
        """`fasta_path` is accepted only for call-signature parity with `run_amrfinder`
        -- its content is never read; the fixture is selected purely by `genome_id`.
        """
        del fasta_path
        fixture_path = self._fixture_dir / f"{genome_id}.tsv"
        source = f"mock:{fixture_path}"
        if not fixture_path.exists():
            return AnnotationResult(
                ok=False,
                source=source,
                error=f"no fixture TSV for genome_id={genome_id!r} at {fixture_path}",
            )
        try:
            features = parse_amrfinder_tsv(fixture_path)
        except (ValidationError, KeyError, ValueError) as exc:
            return AnnotationResult(
                ok=False,
                source=source,
                error=f"fixture TSV at {fixture_path} did not match the expected shape: {exc}",
            )
        return AnnotationResult(
            ok=True, source=source, data=features, amrfinder_db_version=PINNED_DB_VERSION
        )
