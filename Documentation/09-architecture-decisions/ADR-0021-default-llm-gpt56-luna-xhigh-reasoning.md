# ADR-0021 — Default LLM: GPT-5.6 Luna at Extra-High reasoning (temperature omitted)

- **Date:** 2026-07-19
- **Status:** Accepted
- **Origin:** Human-directed (the user selected the model + effort); **agent-verified live** against the OpenAI API before adoption.

## Context

EPIC 5's `OpenAIBackend` (ADR-0006) was scaffolded against `gpt-4o-2024-08-06` with a hard-coded
`temperature=0`. The user directed that the production narrative/reviewer run on OpenAI's
`gpt-5.6-luna` **reasoning** model at "Extra High" reasoning. Reasoning models differ from classic
chat models in two request-shape ways that had to be verified, not assumed, before adoption.

## Decision

Default `OPENAI_MODEL=gpt-5.6-luna` and `OPENAI_REASONING_EFFORT=xhigh` (both configurable via env /
`LLMSettings`). The backend now sends `reasoning_effort` and **omits** `temperature`; each is
optional and included only when set, so the request stays valid for whatever model is configured.
Verified live against the account's API:

- `gpt-5.6-luna` is a real, available model (`GET /v1/models`).
- `reasoning_effort` accepts exactly `none | low | medium | high | xhigh` (from the API's own 400
  on an invalid value); **`xhigh` is the "Extra High" tier**.
- The model **rejects any `temperature` other than the default (1)** ("Unsupported value:
  'temperature' does not support 0 with this model").
- The full `narrate_report` pipeline (narrator + reviewer) was smoke-tested against the live model
  at `low` (accepted, grounding 1.0) and `xhigh` (one run accepted with grounding 1.0; one run's
  reviewer set `overall_pass=false` → **fail-closed to the deterministic template**). Structured
  outputs parse; no token exhaustion. CI remains **mock-only** (no key, no network).

## Consequences

- (+) Strongest available reasoning for grounded narration; the safety machinery (no verdict field
  on any LLM schema, deterministic pre-check, fail-closed template, disclaimer) is unchanged and now
  validated end-to-end against a live reasoning model.
- (−) Reasoning models run at temperature 1 (non-deterministic), so the LLM narrative varies
  run-to-run and is accepted/rejected accordingly — the deterministic template is the guaranteed
  floor. `xhigh` adds latency (~10–20 s/call, two calls per report) and cost.
- (−) Model and `reasoning_effort` are **coupled**: a non-reasoning model must set
  `OPENAI_REASONING_EFFORT` to a value it accepts, or the backend must omit it.
- No prediction depends on the LLM (golden rule #1 unchanged); this is a provider-config decision
  within the ADR-0006 boundary, not a change to it.
- Pinned by `tests/llm/test_openai_backend.py` (reasoning_effort sent + temperature omitted;
  temperature sent only when configured) and `tests/llm/test_factory.py` (config propagates).
