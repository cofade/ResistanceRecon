"""BM25 lexical retrieval sanity over the real seed corpus."""

from __future__ import annotations

from genome_firewall.kb.corpus import load_corpus
from genome_firewall.kb.retriever import BM25Retriever


def _top_chunk_id(query: str) -> str:
    corpus = load_corpus()
    retriever = BM25Retriever(corpus)
    return corpus[retriever.rank(query)[0]].chunk_id


def test_carbapenemase_query_ranks_kpc_first() -> None:
    assert _top_chunk_id("blaKPC carbapenemase meropenem") == "kpc"


def test_sulfonamide_query_ranks_sul_first() -> None:
    assert _top_chunk_id("sul sulfonamide dihydropteroate") == "sul"


def test_ranking_is_deterministic() -> None:
    corpus = load_corpus()
    retriever = BM25Retriever(corpus)
    assert retriever.rank("armA methyltransferase") == retriever.rank("armA methyltransferase")
