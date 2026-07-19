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

## 10.4 Realization status (EPIC 3 PR-B)

PR-B completes the *Safety & honesty* row — first-class no-call, evidence integrity, and fail-loud version safety:

- **First-class no-call (conformal)** — `predictor/conformal.py` fits class-conditional (Mondrian) LAC split-conformal thresholds ([ADR-0004](../09-architecture-decisions/ADR-0004-calibration-and-conformal-prediction-for-no-call.md)); `predict.py` maps the prediction set to a verdict via `schemas.verdict_for_conformal_set` ({S}→work, {R}→fail, {S,R}→no-call ambiguous, {}→no-call novel/OOD). Coverage is fit on the calibration fold and reported empirically on the INDEPENDENT test fold, with an α-sensitivity table over {0.05, 0.10, 0.20} (`models/results_summary.json`).
- **Guarantee-availability is surfaced, never stripped** — when a per-drug calibration set is below the finite-sample floor (n ≥ ⌈1/α⌉−1 per class), `conformal_guarantee_available` is `false` and every affected verdict carries an explicit `statistical_association` caveat in `supporting_features` (not only the model card). The flag reflects calibration-set *size*, not model quality, so a guarantee-void-but-strong model (e.g. gentamicin, AUROC 0.875) is flagged, not silently discarded or downgraded.
- **Evidence integrity (Ground-Truth-First)** — `known_mechanism` (gate) vs `statistical_association` (model). Per-genome statistical evidence cites the FULL signed L2-LR coefficient of each PRESENT feature (the exact closed-form linear attribution), so a genome carrying any resistance determinant can never be reported as having "no known determinants".
- **Fail-loud version safety** — a genome whose AMRFinderPlus DB version, feature `schema_version`, or engineered-feature spec version disagrees with the trained models raises a typed error (`AmrfinderDbVersionMismatchError` / `FeatureSchemaMismatchError`) before ANY verdict, on both `predict_genome` and the single-drug `predict_antibiotic` entry. Novel genes absent from the vocabulary are dropped as OOV, not an error.
- **Real-run coverage (130-genome/67-ST subset)** — gate-negative headline metrics + conformal behaviour are recorded per drug in `models/results_summary.json` and `model_card.md`; the beta-lactam gate-negative residual is thin (`conformal_guarantee_available=false` for 4/5) and flagged as technical debt (§11), not hidden.

## 10.5 Realization status (EPIC 4 + 5 — Decision Report & LLM narrative)

Module 03a implements the *Evidence honesty*, *LLM must never decide*, *Human stays in the loop*, and *External tool fails* rows above:

- **Known vs statistical evidence** — `report/evidence.py` sets `evidence_category` deterministically by curated-KB membership (`features/mechanisms.py`), never by the LLM; the row category is the strongest cited item ([ADR-0020](../09-architecture-decisions/ADR-0020-evidence-tagging-and-fail-closed-narrative-envelope.md)). Pinned by `tests/report/test_evidence.py`, `tests/report/test_builder_validators.py`.
- **LLM must never decide** — `report/nl_schemas.py` (`NLReportSection`, `ReportVerdict`) carry no verdict/confidence/SIR field; `report/pipeline.py`'s `NarrativeEnvelope` keeps the review outcome machine-readable without touching the frozen report. Pinned by `tests/report/test_nl_schemas.py` + the still-green import-boundary gate (`tests/report/test_safety_invariants.py`).
- **Human stays in the loop** — the disclaimer is present on every narrative branch (accepted / rejected / disabled), verified by `tests/report/test_safety_invariants.py`.
- **External tool / LLM fails mid-demo** — `report/reviewer.py` runs a deterministic pre-check *before* any LLM call and `report/pipeline.py` fails closed to the deterministic template on disable, error, or rejection (`review_status` records which). Pinned by `tests/report/test_pipeline.py` and integration shape #5 (`tests/report/test_integration_narrative_shape5.py`).
- **Offline-safe evidence RAG** — hybrid BM25 + optional dense retrieval with RRF, the dense leg behind an `Embedder` Protocol so CI never loads model weights ([ADR-0019](../09-architecture-decisions/ADR-0019-evidence-rag-offline-embedding-and-rrf.md)). Pinned by `tests/kb/`.
