# 10. Quality Requirements

## 10.1 Quality tree (priority order)

1. **Safety & honesty** — calibration, first-class no-call, evidence integrity, mandatory disclaimer.
2. **Correctness** — no data leakage (homology split); deterministic, LLM-free prediction path.
3. **Reproducibility** — pinned tools/DB, versioned artifacts, append-only decision log.
4. **Maintainability** — six-layer SE, quality gates, arc42 docs.
5. **Demo quality** — clear, on-theme, resilient to outages.

## 10.2 Quality scenarios (mapped to challenge success criteria + responsibility requirements)

| Scenario | System response | Measured by |
|---|---|---|
| A confident-but-wrong verdict would harm | Weak / conflicting / OOD evidence → NO-CALL | no-call rate + accuracy-on-called |
| Confidence must be trustworthy | Calibrated probabilities | Brier score + reliability diagram |
| Must generalize beyond seen clones | Report on unseen genetic groups | per-group + leave-one-group-out metrics |
| Class imbalance hides missed resistance | Resistant-recall elevated to a headline metric | balanced accuracy, R & S recall, PR-AUC |
| Evidence must be honest | Known mechanism vs statistical association separated | `evidence_category` audit; reviewer flags causal language on statistical items |
| LLM must never decide | Prediction path is LLM-free | CI import-boundary test |
| Human stays in the loop | Disclaimer on every report | 3-point enforcement test (schema + reviewer + UI) |
| External tool fails mid-demo | Graceful `{ok:false}` envelope → 503 / deterministic fallback | manual outage rehearsal |

These trace directly to the challenge's *Success Criteria* and *Responsibility Requirement* sections (see [`01-introduction-and-goals/challenge-brief.md`](../01-introduction-and-goals/challenge-brief.md)).

## 10.3 Realization status (EPIC 3 PR-A)

The Predictor's training foundation implements the *Correctness* and *Confidence* rows above:

- **No data leakage** — `predictor/split.py` (MLST-ST grouping + singleton fallback, [ADR-0015](../09-architecture-decisions/ADR-0015-homology-split-mlst-singleton-fallback.md)) enforces group-disjoint train/calibration/test/holdout via `no_leakage_check`; a too-clonal drug (fewer than `MIN_DISTINCT_GROUPS` groups) is reported *insufficient data* rather than split unsafely.
- **Generalize beyond clones** — an explicit leave-one-group-out unseen-lineage holdout plus `per_fold_class_balance` (flags StratifiedGroupKFold degradation on a dominant clone).
- **Class imbalance / R-recall headline** — `predictor/train.py` uses `class_weight='balanced'`, PR-AUC-scored C selection, and reports resistant-recall as the headline metric on the gate-negative subset.
- **Trustworthy confidence** — `predictor/calibration.py` sigmoid calibration on the homology-grouped fold ([ADR-0004](../09-architecture-decisions/ADR-0004-calibration-and-conformal-prediction-for-no-call.md); Brier + reliability). First-class no-call (conformal) and evidence-integrity/no-call surfacing land in PR-B.
- **Known vs statistical evidence** — the one-directional gate ([ADR-0018](../09-architecture-decisions/ADR-0018-deterministic-gate-one-directional.md)) tags deterministic hits `known_mechanism`; model coefficients are `statistical_association` (assembled in PR-B's report path).
