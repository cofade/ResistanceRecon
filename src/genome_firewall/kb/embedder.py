"""Dense-embedding backends behind a Protocol.

CI/tests use ``HashingBagOfWordsEmbedder`` -- deterministic, numpy-only, no model download --
so the dense retrieval leg and RRF fusion are exercised fully offline. Production wires
``SentenceTransformerEmbedder``, which constructs the model lazily on first ``embed`` and is
therefore never built in CI (mirrors the AMRFinderPlus isolation pattern). Token hashing uses
BLAKE2b, not Python's per-process ``hash``, so vectors are byte-identical across runs.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Sequence
from typing import Protocol

import numpy as np
from numpy.typing import NDArray

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def tokenize(text: str) -> list[str]:
    """Lowercase alphanumeric tokenization shared by BM25 and the hashing embedder."""
    return _TOKEN_RE.findall(text.lower())


class Embedder(Protocol):
    """Maps texts to an ``(n, dim)`` array of L2-normalized row vectors."""

    def embed(self, texts: Sequence[str]) -> NDArray[np.float64]: ...


def _token_bucket(token: str, dim: int) -> int:
    digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
    return int.from_bytes(digest, "big") % dim


class HashingBagOfWordsEmbedder:
    """Deterministic feature-hashing bag-of-words embedder (no network, no model weights)."""

    def __init__(self, dim: int = 256) -> None:
        self._dim = dim

    def embed(self, texts: Sequence[str]) -> NDArray[np.float64]:
        matrix = np.zeros((len(texts), self._dim), dtype=np.float64)
        for i, text in enumerate(texts):
            for token in tokenize(text):
                matrix[i, _token_bucket(token, self._dim)] += 1.0
            norm = float(np.linalg.norm(matrix[i]))
            if norm > 0.0:
                matrix[i] /= norm
        return matrix


class SentenceTransformerEmbedder:
    """Production semantic embedder. The model is loaded lazily on first ``embed`` and is
    never constructed in CI (importing this module must not require the SDK or the network)."""

    def __init__(self, model_name: str = "all-MiniLM-L6-v2") -> None:
        self._model_name = model_name
        self._model: object | None = None

    def _ensure_model(self) -> object:
        if self._model is None:  # pragma: no cover - real model load, never in CI
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self._model_name)
        return self._model

    def embed(self, texts: Sequence[str]) -> NDArray[np.float64]:  # pragma: no cover - real model
        model = self._ensure_model()
        vectors = model.encode(list(texts), normalize_embeddings=True)  # type: ignore[attr-defined]
        return np.asarray(vectors, dtype=np.float64)
