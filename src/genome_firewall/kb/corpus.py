"""The AMR-mechanism KB corpus: a small, committed, curated set of mechanism chunks read from
``kb/seed/``. Retrieval-only evidence context -- it never sets a category or a verdict.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from pydantic import BaseModel, ConfigDict

_SEED_DIR = Path(__file__).parent / "seed"


class KBChunk(BaseModel):
    """One citable knowledge-base chunk about a resistance-mechanism gene family."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    chunk_id: str
    gene_family: str
    drugs: tuple[str, ...] = ()
    text: str
    source: str


def _read_jsonl(path: Path) -> Iterator[KBChunk]:
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped:
            yield KBChunk.model_validate_json(stripped)


def load_corpus(seed_dir: Path | None = None) -> tuple[KBChunk, ...]:
    """Load every ``*.jsonl`` chunk file under the seed dir, de-duplicated by ``chunk_id``.

    Deterministic: files are read in sorted order and the first occurrence of a ``chunk_id``
    wins, so the hand-curated corpus takes precedence over any dev-generated catalog slice.
    """
    directory = seed_dir or _SEED_DIR
    seen: dict[str, KBChunk] = {}
    for path in sorted(directory.glob("*.jsonl")):
        for chunk in _read_jsonl(path):
            seen.setdefault(chunk.chunk_id, chunk)
    return tuple(seen.values())
