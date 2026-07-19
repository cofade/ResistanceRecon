# ADR-0014 — MLflow local-file experiment tracking (off the inference path)

- **Date:** 2026-07-19
- **Status:** Accepted
- **Origin:** Agent-proposed / human-approved (EPIC 3 PR-B, issue #22). Reuse of a proven component.

## Context

The EPIC 3 training run trains, calibrates, and conformalizes the five per-drug models with per-fold + unseen-lineage-holdout metrics, a C-grid search, conformal α-sensitivity, and several artifacts (metrics.json, model_card.md, conformal.json). Re-running and comparing runs needs experiment tracking — params, metrics, artifacts, lineage. The `tracking` extra already pins `mlflow>=2.14`, `./mlruns` is already gitignored, and `mlflow.*` is already in the mypy override list (EPIC 0 scaffolding). A proven, crash-safe `MLflowTracker` exists in the reference project `digitalsreeni-image-annotator`. So the choice is a **port + ADR**, not a new dependency.

## Decision

Track training with MLflow against a **local file store** (`<project>/mlruns`, gitignored), via a **ported and slimmed** `MLflowTracker` + `NullTracker` in `predictor/experiment_tracking.py`.

Kept from the reference implementation: the tracker/null split; lazy `import mlflow` inside each method (broken/absent mlflow can't stop import or training); blanket crash-safety (a tracking error degrades that run to *untracked*, never aborts training); `to_mlflow_uri()` (a bare Windows drive path is parsed by MLflow as URI scheme `c` and rejected → converted to a `file://` URI); the `MLFLOW_ALLOW_FILE_STORE=true` opt-out (mlflow 3.x raises on the file store otherwise, silently degrading the documented default to untracked); and a cached `mlflow_available()`. Dropped: all Qt/PyQt signals, the run-deep-link URL builders, and the browser-launching `mlflow ui` server (GUI coupling).

Tracking is **strictly off the inference/verdict path**. `predictor/predict.py` never imports it; a run with tracking entirely absent (the `NullTracker` default that `train_and_register` uses when no tracker is passed) produces byte-identical models. `mlflow` stays an optional extra — every use is lazy and guarded, so the package imports and trains without it.

## Consequences

- (+) Reproducible, comparable training runs (params + metrics + artifacts) at **zero** new-dependency cost (extra + gitignore + mypy override already existed) and zero GUI baggage.
- (+) A tracking failure can never corrupt or abort a training run, and never touches a verdict — proven by the `NullTracker` byte-identical property and the crash-safety test (`tests/predictor/test_experiment_tracking.py`).
- (−) Local file store only (no remote/DB backend) — sufficient for the single-machine hackathon run; a remote URI is a one-line `tracking_uri` change later.
- (−) `experiment_tracking.py` lives under `predictor/` but is **non-trust-critical**; its thin mlflow-live wrappers are covered only when the `tracking` extra is installed (always true under `uv sync --all-extras`, including CI). The crash-safety + null-inert branches are covered unconditionally.
- Recorded in `Documentation/reuse-inventory.md` (gitignored). Pinned by `tests/predictor/test_experiment_tracking.py`.
