"""Evidence RAG: retrieve cited KB context for the genes AMRFinderPlus detected.

Retrieval-only. It returns text + provenance to enrich the LLM narrative's citations; it never
sets an ``evidence_category`` and never decides a verdict (that stays deterministic in
``report/evidence.py`` and ``predictor/``).
"""

from __future__ import annotations

from collections.abc import Sequence

from genome_firewall.kb.corpus import load_corpus
from genome_firewall.kb.embedder import Embedder
from genome_firewall.kb.retriever import HybridRetriever, RetrievedChunk


class EvidenceRAG:
    """Thin wrapper over the hybrid retriever, keyed on detected genes + the drug in question."""

    def __init__(self, retriever: HybridRetriever) -> None:
        self._retriever = retriever

    @classmethod
    def from_seed(cls, *, embedder: Embedder | None = None) -> EvidenceRAG:
        """Build a retriever over the committed seed corpus (BM25-only without an embedder)."""
        return cls(HybridRetriever(load_corpus(), embedder=embedder))

    def retrieve_for_genes(
        self, genes: Sequence[str], drug: str, *, k: int = 5
    ) -> tuple[RetrievedChunk, ...]:
        """Retrieve the top-``k`` cited chunks for a drug given the detected gene symbols."""
        query = " ".join([drug, *genes]).strip()
        if not query:
            return ()
        return self._retriever.retrieve(query, k=k)
