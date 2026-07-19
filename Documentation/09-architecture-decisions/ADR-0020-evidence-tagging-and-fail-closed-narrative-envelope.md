# ADR-0020 — Evidence-category tagging policy & the fail-closed narrative envelope

- **Date:** 2026-07-19
- **Status:** Accepted
- **Origin:** Agent-proposed / human-approved (EPIC 4+5 planning session, issues #23/#26).
  **Safety-critical.**

## Context

The deterministic report builder (EPIC 4) must set each row's `evidence_category`
(KNOWN_MECHANISM / STATISTICAL_ASSOCIATION / NO_SIGNAL) honestly (golden rule #3), and the LLM
narrative (EPIC 5) must fail closed when it cannot be trusted (ADR-0006). Two decisions were open:

1. **What anchors the KNOWN_MECHANISM tag** — the deterministic *gate firing* (narrow: only when
   the gate forces `likely_to_fail`) or *curated-KB membership* (broader: any gene/mutation that
   is a known mechanism, per `features/mechanisms.py`). A gate-anchored row-category rule trips
   the `AntibioticPrediction` validator when a lone KB-member gene (e.g. a single `qnrB`) is
   present but the gate did not fire: the row would be labelled `statistical_association` while
   the only cited item is `known_mechanism`.
2. **Where the LLM review outcome is recorded**, given `GenomeReport` is frozen
   (`schemas.py`, `extra='forbid'`) and carries only `narrative_summary: str | None`.

## Decision

**Tagging (deterministic, LLM-free):**
- Per-`EvidenceItem`: a supporting gene/mutation is `known_mechanism` **iff it is a member of the
  curated mechanism KB for that drug** (`features/mechanisms.py` predicates — the same source the
  gate uses); any feature the model merely weighted is `statistical_association`.
- Row-level `evidence_category` = the **strongest category among the cited items**
  (`known_mechanism` > `statistical_association` > `no_signal`). This satisfies all three
  `AntibioticPrediction` validators by construction and eliminates the lone-KB-member footgun.
- A gate hit still forces `likely_to_fail` at `KNOWN_MECHANISM_CONFIDENCE = 0.99` (ADR-0018);
  every other row keeps the calibrated model confidence, even when it is `known_mechanism`.
  **Category and confidence are independent axes** — a present known-mechanism gene never inflates
  a non-gate confidence to 0.99.

**Fail-closed narrative:**
- The reviewer runs a **deterministic pre-check before any LLM call** — a fabricated number, a
  drug not evaluated, a verdict word the report never made, or causal language on a
  statistical/no-signal row rejects outright.
- The pipeline returns a **`NarrativeEnvelope` alongside the report** (mirroring the `{ok, source,
  error}` pattern) carrying `review_status ∈ {llm_output_accepted, llm_output_rejected,
  llm_disabled}` and `source ∈ {llm, template}` — the frozen `GenomeReport` is not modified, and
  the review outcome stays machine-readable. Any disable/error/rejection falls back to the
  deterministic template; the disclaimer is present on every branch.

Rejected: gate-anchored row category (validator footgun, and less honest — it would deny that a
present known-mechanism gene is a known mechanism); mutating `GenomeReport` to add a status field
(breaks the frozen contract).

## Consequences

- (+) Honest, auditable, reproducible KNOWN vs STATISTICAL separation with no LLM involvement;
  validators hold across the whole synthetic cohort.
- (+) A load-bearing (not advisory) review gate that costs nothing extra because the deterministic
  template must exist as the no-API-key fallback anyway.
- (−) A present-but-non-gating known mechanism yields a `known_mechanism` row at model confidence,
  which the narrative must word carefully (mechanism present, model-driven verdict) — enforced by
  the reviewer's causal-language check.
- Pinned by `tests/report/test_builder_validators.py`, `tests/report/test_evidence.py`,
  `tests/report/test_reviewer.py`, `tests/report/test_pipeline.py`, and
  `tests/report/test_safety_invariants.py`.
