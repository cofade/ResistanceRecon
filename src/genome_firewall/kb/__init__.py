"""AMR-mechanism knowledge base: hybrid BM25 + embedding + RRF retrieval for evidence
context and citations. Retrieval-only — never adjudicates a verdict."""

from __future__ import annotations

from genome_firewall.kb.corpus import KBChunk, load_corpus
from genome_firewall.kb.embedder import (
    Embedder,
    HashingBagOfWordsEmbedder,
    SentenceTransformerEmbedder,
)
from genome_firewall.kb.evidence_rag import EvidenceRAG
from genome_firewall.kb.retriever import RRF_K, HybridRetriever, RetrievedChunk

__all__ = [
    "RRF_K",
    "Embedder",
    "EvidenceRAG",
    "HashingBagOfWordsEmbedder",
    "HybridRetriever",
    "KBChunk",
    "RetrievedChunk",
    "SentenceTransformerEmbedder",
    "load_corpus",
]
