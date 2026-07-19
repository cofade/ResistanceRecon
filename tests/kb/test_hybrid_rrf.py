"""Hybrid retriever + RRF fusion, exercised fully offline with a deterministic fake embedder."""

from __future__ import annotations

from genome_firewall.kb.embedder import HashingBagOfWordsEmbedder
from genome_firewall.kb.retriever import RRF_K, HybridRetriever
from tests.kb.conftest import TINY_CORPUS, FakeEmbedder


def test_rrf_k_is_the_standard_constant() -> None:
    assert RRF_K == 60


def test_bm25_only_when_no_embedder() -> None:
    retriever = HybridRetriever(TINY_CORPUS)
    assert retriever.is_hybrid is False
    results = retriever.retrieve("alpha carbapenemase", k=3)
    assert results[0].chunk.chunk_id == "alpha"
    # One leg only: max fused score is 1/(RRF_K+1).
    assert results[0].score <= 1.0 / (RRF_K + 1) + 1e-9


def test_hybrid_fuses_both_legs() -> None:
    retriever = HybridRetriever(TINY_CORPUS, embedder=FakeEmbedder())
    assert retriever.is_hybrid is True
    results = retriever.retrieve("alpha carbapenemase", k=3)
    # 'alpha' is ranked top by BOTH legs (BM25 lexical + the fake dense embedder), so it wins
    # and its fused score exceeds the single-leg ceiling -> both legs contributed.
    assert results[0].chunk.chunk_id == "alpha"
    assert results[0].score > 1.0 / (RRF_K + 1)
    assert results[0].score <= 2.0 / (RRF_K + 1) + 1e-9


def test_retrieval_scores_are_sorted_descending_and_deterministic() -> None:
    retriever = HybridRetriever(TINY_CORPUS, embedder=HashingBagOfWordsEmbedder())
    first = retriever.retrieve("beta methyltransferase", k=3)
    second = retriever.retrieve("beta methyltransferase", k=3)
    scores = [r.score for r in first]
    assert scores == sorted(scores, reverse=True)
    assert [r.chunk.chunk_id for r in first] == [r.chunk.chunk_id for r in second]


def test_k_limits_results() -> None:
    retriever = HybridRetriever(TINY_CORPUS, embedder=FakeEmbedder())
    assert len(retriever.retrieve("resistance", k=2)) == 2
