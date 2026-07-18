# ADR-0003 — Per-antibiotic regularized logistic regression (classical ML is the star)

- **Date:** 2026-07-18
- **Status:** Accepted
- **Origin:** Human.

## Context

The challenge recommends one regularized logistic-regression model per antibiotic on AMRFinderPlus features as a dependable, CPU-friendly, explainable core. Deep genomic LMs are an optional stretch.

## Decision

One independent binary classifier per antibiotic: `LogisticRegression(penalty='l2', class_weight='balanced', solver='lbfgs', max_iter=2000)`, `C` chosen by inner grouped CV. L2 (not L1) because AMR genes co-occur on plasmids/operons and L1 arbitrarily zeroes correlated markers. Per-drug (not multilabel) because mechanisms/prevalence differ and BV-BRC labels are sparse/MNAR per isolate; per-drug also enables independent calibration, conformal alpha, and evidence.

## Consequences

- (+) Fast, calibratable, explainable, robust when features ≈ samples; per-drug evidence for the report.
- (−) Drugs with thin labels need a min-n gate (≥20 R / ≥20 S) → "insufficient data" no-call.
- Deep-learning embeddings remain a documented follow-on. Detail: [research-findings/ml-methodology.md](../research-findings/ml-methodology.md).
