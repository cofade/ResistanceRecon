"""Embedder tests: the hashing embedder is deterministic/offline; the SentenceTransformer
embedder is never constructed (no model load, no network) at build time."""

from __future__ import annotations

import numpy as np

from genome_firewall.kb.embedder import (
    HashingBagOfWordsEmbedder,
    SentenceTransformerEmbedder,
    tokenize,
)


def test_hashing_embedder_is_deterministic_and_normalized() -> None:
    embedder = HashingBagOfWordsEmbedder(dim=64)
    first = embedder.embed(["blaKPC carbapenemase"])
    second = embedder.embed(["blaKPC carbapenemase"])
    assert np.array_equal(first, second)  # deterministic across calls
    assert first.shape == (1, 64)
    assert abs(float(np.linalg.norm(first[0])) - 1.0) < 1e-9  # L2-normalized


def test_hashing_embedder_handles_empty_text() -> None:
    matrix = HashingBagOfWordsEmbedder(dim=16).embed([""])
    assert float(np.linalg.norm(matrix[0])) == 0.0  # no tokens -> zero vector, no divide-by-zero


def test_tokenize_lowercases_and_splits_on_non_alphanumeric() -> None:
    assert tokenize("blaKPC-2, ompK36!") == ["blakpc", "2", "ompk36"]


def test_sentence_transformer_embedder_does_not_load_the_model_at_construction() -> None:
    embedder = SentenceTransformerEmbedder("all-MiniLM-L6-v2")
    # Constructing the wrapper must not build the model or touch the network.
    assert embedder._model is None
