"""EvidenceRAG is retrieval-only: it returns cited chunks + provenance, never a category."""

from __future__ import annotations

from genome_firewall.kb.embedder import HashingBagOfWordsEmbedder
from genome_firewall.kb.evidence_rag import EvidenceRAG
from genome_firewall.kb.retriever import RetrievedChunk


def test_retrieve_for_genes_returns_cited_chunks() -> None:
    rag = EvidenceRAG.from_seed(embedder=HashingBagOfWordsEmbedder())
    results = rag.retrieve_for_genes(["armA"], "gentamicin", k=3)
    assert results
    assert all(isinstance(r, RetrievedChunk) for r in results)
    assert results[0].chunk.chunk_id == "armA_rmt"
    assert all(r.chunk.source for r in results)  # provenance carried


def test_retrieved_chunk_carries_no_verdict_or_category_field() -> None:
    # Golden rule #1 / #3: retrieval never adjudicates. The chunk schema has no such field.
    forbidden = {"verdict", "evidence_category", "confidence", "calibrated_confidence"}
    assert forbidden.isdisjoint(RetrievedChunk.model_fields)
    from genome_firewall.kb.corpus import KBChunk

    assert forbidden.isdisjoint(KBChunk.model_fields)


def test_empty_query_returns_nothing() -> None:
    rag = EvidenceRAG.from_seed()
    assert rag.retrieve_for_genes([], "", k=3) == ()
