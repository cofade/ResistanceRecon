"""Guard: the full evidence-RAG path never constructs a SentenceTransformer in CI.

If any code path tried to build the real model it would download weights (network) -- the
autouse ``_no_network`` guard is the backstop, but this test makes the invariant explicit by
replacing ``sentence_transformers.SentenceTransformer`` with a sentinel that raises if called.
"""

from __future__ import annotations

import sys
from types import ModuleType
from typing import Any

import pytest

from genome_firewall.kb.embedder import HashingBagOfWordsEmbedder
from genome_firewall.kb.evidence_rag import EvidenceRAG


def _install_exploding_sentence_transformers(monkeypatch: pytest.MonkeyPatch) -> None:
    def _boom(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("SentenceTransformer must not be constructed in CI")

    module = sys.modules.get("sentence_transformers")
    if module is None:
        module = ModuleType("sentence_transformers")
        monkeypatch.setitem(sys.modules, "sentence_transformers", module)
    monkeypatch.setattr(module, "SentenceTransformer", _boom, raising=False)


def test_rag_path_never_builds_sentence_transformer(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_exploding_sentence_transformers(monkeypatch)
    rag = EvidenceRAG.from_seed(embedder=HashingBagOfWordsEmbedder())
    results = rag.retrieve_for_genes(["blaKPC-2"], "meropenem", k=3)
    assert results
    assert results[0].chunk.chunk_id == "kpc"
