# ADR-0004 — Sigmoid calibration + conformal prediction for the no-call

- **Date:** 2026-07-18
- **Status:** Accepted
- **Origin:** Agent-proposed / human-approved.

## Context

The challenge scores calibration quality (Brier, reliability) and rewards a principled no-call. A confident-but-wrong result is the dangerous failure mode.

## Decision

Calibrate with `CalibratedClassifierCV(method='sigmoid', cv='prefit')` on a self-constructed **homology-grouped** calibration fold (isotonic only for rare high-n/high-prevalence drugs). Layer conformal prediction on the calibrated probabilities: **crepes** Mondrian (class/group-conditional) as primary, **MAPIE** (LAC) as cross-check. Prediction sets map to verdicts: `{S}`→work, `{R}`→fail, `{S,R}`→no-call (ambiguous), `{}`→no-call (novel/OOD). Default alpha 0.10 with a documented sensitivity table over {0.05, 0.10, 0.20}.

## Consequences

- (+) Coverage-guaranteed, honest abstention; calibrated confidence surfaced alongside the conformal set.
- (−) Small per-drug calibration folds may be below stable-quantile floors → mark "conformal guarantee unavailable" distinct from a per-genome no-call.
- Note: `CalibratedClassifierCV`'s internal CV is not group-aware, hence `cv='prefit'`. Detail: [research-findings/ml-methodology.md](../research-findings/ml-methodology.md).
