"""Shared helpers for kb tests: a tiny corpus and a deterministic fake embedder that yields a
controlled dense ranking (so RRF fusion can be asserted exactly, offline)."""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
from numpy.typing import NDArray

from genome_firewall.kb.corpus import KBChunk

TINY_CORPUS = (
    KBChunk(
        chunk_id="alpha",
        gene_family="alphaGene",
        drugs=("meropenem",),
        text="alpha carbapenemase resistance",
        source="test",
    ),
    KBChunk(
        chunk_id="beta",
        gene_family="betaGene",
        drugs=("gentamicin",),
        text="beta methyltransferase resistance",
        source="test",
    ),
    KBChunk(
        chunk_id="gamma",
        gene_family="gammaGene",
        drugs=("ciprofloxacin",),
        text="gamma quinolone resistance",
        source="test",
    ),
)


class FakeEmbedder:
    """Deterministic 2-d embedder: 'alpha' texts -> [1,0], everything else -> [0,1]."""

    def embed(self, texts: Sequence[str]) -> NDArray[np.float64]:
        rows = [[1.0, 0.0] if "alpha" in t.lower() else [0.0, 1.0] for t in texts]
        return np.asarray(rows, dtype=np.float64)
