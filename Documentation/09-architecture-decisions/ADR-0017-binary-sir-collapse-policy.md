# ADR-0017 — Binary SIR collapse policy: Resistant/Susceptible only

- **Date:** 2026-07-19
- **Status:** Accepted
- **Origin:** Human-decided (EPIC 3 planning session, issue #18).

## Context

EPIC 1 deliberately kept the full SIR vocabulary (Resistant, Susceptible, Intermediate, Nonsusceptible, Susceptible-dose dependent) through label ingestion; collapsing to the binary R/S target the per-drug models train on is EPIC 3's responsibility. Intermediate is unambiguously not a training target. Nonsusceptible and Susceptible-dose-dependent (SDD) are rarer and their clinical placement is genuinely in-between.

## Decision

Map only `Resistant → R` and `Susceptible → S`. **DROP** Intermediate, Nonsusceptible, and Susceptible-dose dependent (their rows are removed, not force-mapped) via `predictor/dataset.collapse_sir_to_binary`. The partition is pinned structurally: `constants.BINARY_RESISTANT_CLASSES | BINARY_SUSCEPTIBLE_CLASSES | DROPPED_SIR_CLASSES` must equal the full SIR vocabulary, enforced by an `if/raise` guard at import time (survives `python -O`).

## Consequences

- (+) Lowest label noise — no guessing a binary side for a category whose meaning is in-between or rare; matches the defensive-by-design framing.
- (−) Discards usable rows (Nonsusceptible is arguably R-side); a documented alternative was `Nonsusceptible → R`. Revisit per-drug if a drug's label volume is thin after the grouped split.
- Pinned by `tests/predictor/test_binary_collapse.py`.
