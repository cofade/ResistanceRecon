"""Hybrid BM25 + dense retrieval fused by Reciprocal Rank Fusion (RRF).

BM25 (rank-bm25) is always on and offline. The dense leg is optional -- injected as an
``Embedder``; when present, the two ranked lists are fused by RRF
(score = sum_over_legs 1 / (RRF_K + rank)). With no embedder the retriever degrades to
BM25-only. Ties break deterministically on ``chunk_id`` so results are stable across runs.
"""

from __future__ import annotations

from collections.abc import Sequence

from pydantic import BaseModel, ConfigDict
from rank_bm25 import BM25Okapi

from genome_firewall.kb.corpus import KBChunk
from genome_firewall.kb.embedder import Embedder, tokenize

#: The standard RRF constant (Cormack et al., 2009); dampens the weight of top ranks.
RRF_K = 60


class RetrievedChunk(BaseModel):
    """A corpus chunk plus its fused retrieval score (higher = more relevant)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    chunk: KBChunk
    score: float


def _chunk_text(chunk: KBChunk) -> str:
    return f"{chunk.gene_family} {chunk.text}"


class BM25Retriever:
    """Lexical BM25 ranking over the corpus."""

    def __init__(self, corpus: Sequence[KBChunk]) -> None:
        self._corpus = tuple(corpus)
        self._bm25 = BM25Okapi([tokenize(_chunk_text(c)) for c in self._corpus])

    def rank(self, query: str) -> list[int]:
        scores = self._bm25.get_scores(tokenize(query))
        return sorted(
            range(len(self._corpus)),
            key=lambda i: (-float(scores[i]), self._corpus[i].chunk_id),
        )


class DenseRetriever:
    """Cosine ranking over injected dense embeddings (vectors are L2-normalized)."""

    def __init__(self, corpus: Sequence[KBChunk], embedder: Embedder) -> None:
        self._corpus = tuple(corpus)
        self._embedder = embedder
        self._matrix = embedder.embed([_chunk_text(c) for c in self._corpus])

    def rank(self, query: str) -> list[int]:
        query_vec = self._embedder.embed([query])[0]
        similarities = self._matrix @ query_vec
        return sorted(
            range(len(self._corpus)),
            key=lambda i: (-float(similarities[i]), self._corpus[i].chunk_id),
        )


class HybridRetriever:
    """BM25 + optional dense leg, fused by RRF."""

    def __init__(
        self,
        corpus: Sequence[KBChunk],
        *,
        embedder: Embedder | None = None,
        rrf_k: int = RRF_K,
    ) -> None:
        self._corpus = tuple(corpus)
        self._bm25 = BM25Retriever(self._corpus)
        self._dense = DenseRetriever(self._corpus, embedder) if embedder is not None else None
        self._rrf_k = rrf_k

    @property
    def is_hybrid(self) -> bool:
        """True when a dense leg is active (BM25 + embeddings), False for BM25-only."""
        return self._dense is not None

    def retrieve(self, query: str, *, k: int = 5) -> tuple[RetrievedChunk, ...]:
        rankings = [self._bm25.rank(query)]
        if self._dense is not None:
            rankings.append(self._dense.rank(query))

        fused: dict[int, float] = {}
        for ranking in rankings:
            for rank, idx in enumerate(ranking):
                fused[idx] = fused.get(idx, 0.0) + 1.0 / (self._rrf_k + rank + 1)

        order = sorted(fused, key=lambda i: (-fused[i], self._corpus[i].chunk_id))
        return tuple(RetrievedChunk(chunk=self._corpus[i], score=fused[i]) for i in order[:k])
