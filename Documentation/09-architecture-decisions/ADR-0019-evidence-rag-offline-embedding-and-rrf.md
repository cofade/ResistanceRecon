# ADR-0019 — Evidence RAG: offline-safe hybrid retrieval (BM25 + optional embedding, RRF)

- **Date:** 2026-07-19
- **Status:** Accepted
- **Origin:** Agent-proposed / human-approved (EPIC 4+5 planning session, issue #24).

## Context

EPIC 5 requires an AMR-mechanism evidence RAG (`kb/`) with "hybrid BM25 + embedding + RRF
retrieval" to enrich the LLM narrative with citations. Two constraints collide:

1. **CI is fully offline, no API keys** (`.github/workflows/ci.yml`), and an autouse
   `_no_network` fixture makes any socket use raise.
2. `sentence-transformers` (the declared `rag` extra) **downloads model weights on first
   `SentenceTransformer(...)` construction** — which would hit the network and fail CI, the same
   class of "heavy external dependency" problem AMRFinderPlus has (ADR-0002).

The alternatives considered: (a) BM25-only, deferring the embedding leg entirely; (b) attempt the
real sentence-transformer in CI; (c) put the dense leg behind an interface with a deterministic,
download-free implementation for CI.

## Decision

`kb/` is a **hybrid retriever with the dense leg behind an `Embedder` Protocol**:

- **BM25** (`rank-bm25`) is always on, pure-Python, offline.
- The **dense leg is optional and injected.** CI/tests use `HashingBagOfWordsEmbedder`
  (deterministic feature-hashing bag-of-words, numpy-only, BLAKE2b token hashing so vectors are
  byte-identical across processes — Python's per-process `hash` is *not* used). This exercises the
  dense leg and the RRF fusion path fully offline. Production wires
  `SentenceTransformerEmbedder`, which constructs the model **lazily on first `embed`** and is
  therefore never built in CI (mirrors the AMRFinderPlus isolation pattern).
- The two ranked lists are fused by **Reciprocal Rank Fusion**, `score = Σ_legs 1/(RRF_K + rank)`
  with **`RRF_K = 60`** (Cormack et al., 2009). Ties break deterministically on `chunk_id`. With
  no embedder the retriever degrades to BM25-only.
- The corpus is a small, committed, hand-curated seed (`kb/seed/mechanism_chunks.jsonl`); the
  2.3 MB `ReferenceGeneCatalog.txt` is **never read in CI** — an offline dev tool
  (`kb/loader.build_catalog_chunks`) distils extra chunks on demand.

Rejected (a): it does not satisfy issue #24's hybrid+RRF requirement. Rejected (b): guaranteed
red CI on the offline weight download.

## Consequences

- (+) The full hybrid + RRF path is genuinely exercised in CI, offline and deterministically; the
  real semantic model swaps in for production/manual use with zero call-site changes.
- (+) Retrieval is retrieval-only — it never sets an `evidence_category` or a verdict (golden
  rules #1/#3); the known-mechanism tag is deterministic (ADR-0020).
- (−) **MVP limitation (stated, not hidden):** the dense leg exercised in CI is a lexical hashing
  embedder, not learned sentence embeddings; `SentenceTransformerEmbedder` is wired but not
  covered by CI (the offline constraint). Recorded in §11.4 as a Known-AI-Pitfall.
- (−) The seed KB is deliberately thin, so some mechanisms are under-cited — an explicit MVP
  limitation for the model card.
- Pinned by `tests/kb/test_hybrid_rrf.py`, `tests/kb/test_no_sentence_transformer_construction.py`,
  and `tests/kb/test_embedder.py`.
