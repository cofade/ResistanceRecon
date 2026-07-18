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
