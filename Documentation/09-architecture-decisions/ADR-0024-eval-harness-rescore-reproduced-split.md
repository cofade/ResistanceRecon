# ADR-0024 — Evaluation harness re-scores committed models on the reproduced homology split

Date: 2026-07-19
Status: Accepted

## Context

EPIC 7 (#29) requires held-out metrics at three granularities — marginal, per genetic group (ST),
and unseen-lineage holdout — for the already-trained per-drug models. The committed
`models/<drug>/v1/metrics.json` already carries test + holdout metrics (marginal + gate-negative),
but NOT the per-ST breakdown, the selective-prediction pair (no-call rate + accuracy-on-called),
reliability bins, or per-slice Brier. Producing those requires re-scoring the persisted models.

Two constraints shape how. (1) `predictor/`, `features/`, `schemas.py`, and the training
orchestration are frozen — Lane B consumes, never modifies them. (2) The split's seed, n_splits,
and backend are NOT persisted with the model (`registry.json` / `results_summary.json` /
`metrics.json` record none of them), so eval must assume the training defaults (seed=0, n_splits=5,
`MlstStBackend`).

## Decision

The eval harness (`src/genome_firewall/eval/`) **re-scores** the committed
`calibrated_model.joblib` on the folds of a **reproduced** homology split
(`predictor.split.make_split` reused verbatim, never re-implemented), with the genome-id ordering
`sorted(set(matrix.index) & set(labels))` identical to training and labels built from the same
`predictor.dataset` primitives.

A wrong assumed seed yields a *different-but-internally-disjoint* split that `no_leakage_check`
cannot distinguish from the correct one — its test fold silently overlaps the genomes the model was
actually trained on. So the harness re-derives the four committed metric sets on the reproduced
folds and asserts they equal `metrics.json` field-for-field (`ReproCheck.committed_match`). This
cross-check is both the anti-leakage guard and the "no vibes numbers" guarantee: a metric ships
only if it is reproducible from a committed artifact. `scripts/run_eval.py` exits non-zero and
refuses to write when any drug diverges.

Metrics are computed on the *served* (gate-negative) population — the one the calibrated model
actually decides at inference — with `classification_metrics` mirroring `predictor.train._metric_set`
bit-for-bit so the cross-check is exact. Eval-result schemas live in `eval/schemas.py`
(reporting-only, consumed by nobody downstream), not the frozen top-level `schemas.py`.

### Alternative considered

**Persist per-genome test predictions at train time, then aggregate (no re-scoring; CI-runnable).**
Rejected: it modifies the frozen training orchestration and creates a second source of truth (a
predictions file that can drift from the `.joblib` model). Re-scoring keeps splitting single-sourced
in `make_split` and is self-verifying via the cross-check.

## Consequences

- The harness needs the feature matrix at eval time, so `run_eval.py` is dev/offline only (never
  CI), exactly like `train_predictor.py`; CI covers the mechanics on the synthetic cohort.
- The assumed seed/n_splits/backend are a latent fragility, mitigated by the cross-check today; a
  future (out-of-scope) improvement is to persist them in `registry.json` so eval need not assume.
- `models/eval_summary.json` is committed as ground-truth alongside `results_summary.json`.
