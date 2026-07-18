# ADR-0006 — LLM boundary: evidence RAG, reviewer, and report narration only

- **Date:** 2026-07-18
- **Status:** Accepted
- **Origin:** Human.

## Context

The hackathon is OpenAI-powered and rewards multimodal/agentic integration, but a hallucinated or uncalibrated prediction from an LLM would be unsafe and would break the calibration story. Classical ML is the star.

## Decision

The LLM is **structurally barred from the prediction path**. Verdicts/confidence are computed only by `predictor/` and passed to the LLM as immutable, read-only context. Three surgical LLM uses: (1) evidence RAG (retrieval-only; the known-mechanism tag is set deterministically by KB-membership), (2) grounded NL report narration (temp 0, structured output, no verdict field), (3) LLM-as-reviewer (deterministic substring/number pre-check, then LLM judge; **fails closed** to the deterministic template with `review_status='llm_output_rejected'`). Enforced by: LLM output schemas that contain no verdict/confidence field, provider-agnostic client with `MockLLMClient` in CI, and a CI import-boundary test (`scripts/check_import_boundary.py`) forbidding `reader/`/`features/`/`predictor/` from importing `llm/`.

## Consequences

- (+) Predictions stay deterministic, auditable, regression-testable; graceful no-API-key degradation; strong responsible-AI story.
- (−) OpenAI structured-output port work; LLM-judge shares a failure-mode ceiling with the generator (mitigated by the deterministic pre-check).
- Detail: [research-findings/llm-boundary.md](../research-findings/llm-boundary.md).
