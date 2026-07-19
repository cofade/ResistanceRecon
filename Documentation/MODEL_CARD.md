# Model Card — Genome Firewall per-antibiotic resistance predictor

> **This is decision support only — confirm every result with standard laboratory antimicrobial
> susceptibility testing before any clinical action.** The system analyses a genome; it never
> designs, modifies, or synthesises one, and it is not a clinical device.

Every number below is reproducible from a committed artifact. The headline (test-fold) metrics
are `models/results_summary.json`; the per-ST and unseen-lineage metrics are
`models/eval_summary.json`, produced by `scripts/run_eval.py` (EPIC 7). The two agree by
construction: the eval harness re-scores the committed models on the *same* homology-grouped
split and asserts its re-derived test-fold metrics equal the committed ones
(`reproducibility.committed_match == true`, max delta `0.0` for all five drugs).

## What this model is

One **independent binary classifier per antibiotic**: L2 logistic regression on
AMRFinderPlus-derived gene/mutation features + a few engineered aggregates, sigmoid
(Platt) probability calibration on a homology-grouped calibration fold, and class-conditional
(Mondrian) split-conformal prediction that maps to a verdict — `{S}`→LIKELY TO WORK,
`{R}`→LIKELY TO FAIL, `{S,R}` or `{}`→NO-CALL. A deterministic **known-mechanism gate** overrides
the model where a called resistance determinant is present (ADR-0018). The LLM never predicts:
verdicts and confidences come only from this pipeline (ADR-0006, enforced by an import-boundary
test).

- **Species:** *Klebsiella pneumoniae* (NCBI taxon 573) only. Anything else is "not covered".
- **Panel:** meropenem, ceftriaxone, ciprofloxacin, gentamicin, trimethoprim-sulfamethoxazole.
- **Served population:** the *gate-negative* genomes — those the deterministic gate does not
  short-circuit. All headline and generalization metrics below are on that population, because
  it is the one the calibrated model actually decides.
- **Provenance:** AMRFinderPlus DB `2026-05-15.1`, feature schema `1.0.0`, 186 features,
  conformal α `0.10`, homology split backend `mlst_st`, seed `0`.

## Training / evaluation data

A **130-genome, 67-homology-group (64 STs + 3 singletons)** subset of BV-BRC lab-measured AST,
annotated with AMRFinderPlus. This is a deliberately thin MVP demonstration cut, **not** the
full labelled dataset (5,227 labelled genomes are available — see `DATASHEET.md`). The split is
homology-aware (MLST-grouped, singleton fallback; ADR-0005/0015): near-identical clones never
straddle a train/test boundary, and one entire ST is held out as the unseen-lineage set.

## Headline metrics — gate-negative test fold

Classification metrics on the grouped test fold (matches `results_summary.json`; re-derived and
cross-checked by the eval harness). `n/a` where a metric is undefined (a single-class fold has
no AUROC; no positives → no PR-AUC) — never a fabricated value.

| Antibiotic | n (R/S) | resistant recall | susceptible recall | balanced acc | AUROC | PR-AUC | conformal guarantee |
|---|---|---|---|---|---|---|---|
| gentamicin | 18 (4/14) | 0.50 | 0.93 | 0.71 | **0.875** | **0.761** | ✗ |
| meropenem | 23 (1/22) | 0.00 | 1.00 | 0.50 | 0.045 | 0.045 | ✗ |
| ceftriaxone | 10 (0/10) | — | 1.00 | 1.00 | n/a | n/a | ✗ |
| ciprofloxacin | 10 (0/10) | — | 1.00 | 1.00 | n/a | n/a | ✗ |
| trimethoprim-sulfamethoxazole | 10 (0/10) | — | 1.00 | 1.00 | n/a | n/a | ✓ |

Brier (calibration fold, `results_summary.json`): gentamicin 0.112, meropenem 0.096, ceftriaxone
0.149, ciprofloxacin 0.007, TMP-SMX 0.089. The eval harness additionally reports test/holdout/
per-ST Brier in `eval_summary.json`.

**Read this honestly:** only **gentamicin** has both classes in its gate-negative test fold, so
it is the only drug whose discrimination (AUROC 0.875) is meaningful. Three drugs have a
**single-class (all-susceptible) test fold** — their `balanced_accuracy = 1.00` is trivial (a
constant "susceptible" call scores perfectly when nothing resistant is present) and AUROC/PR-AUC
are undefined. Meropenem's gate-negative fold has a single resistant genome the model misses
(AUROC 0.045 ≈ a random classifier on one point). None of these are strong evidence of skill;
they are what a 130-genome subset yields after the gate removes the resistant carriers.

## Generalization — unseen-lineage holdout

Metrics on an entire homology group held out of training (the honest generalization signal;
`eval_summary.json`).

| Antibiotic | holdout group | n (R/S) | resistant recall | balanced acc | AUROC | PR-AUC |
|---|---|---|---|---|---|---|
| gentamicin | ST307 | 19 (17/2) | **0.82** | **0.91** | **0.882** | 0.987 |
| ceftriaxone | ST258 | 5 (4/1) | 1.00 | 0.50 | 0.25 | 0.80 |
| meropenem | ST307 | 4 (1/3) | 0.00 | 0.50 | 0.33 | 0.33 |
| ciprofloxacin | ST37 | 4 (0/4) | — | 1.00 | n/a | n/a |
| trimethoprim-sulfamethoxazole | ST307 | 2 (0/2) | — | 1.00 | n/a | n/a |

**Only gentamicin supports a generalization claim.** On an unseen clone (ST307, 19 genomes, both
classes) it holds up — balanced accuracy 0.91, AUROC 0.882, essentially matching its test-fold
AUROC 0.875. The other four holdouts are single-class or n ≤ 5, so no meaningful unseen-lineage
conclusion can be drawn for them; the numbers are reported for completeness, not as evidence.

## Per-ST breakdown & selective prediction

`eval_summary.json` carries per-ST-group metrics for every drug; at n=130 most groups are a
**single genome**, so per-ST numbers are illustrative, not statistical. It also carries the
selective-prediction pair (no-call rate + accuracy-on-called) at every granularity, computed on
the served (gate-negative) population — note this differs from `results_summary.json`'s no-call
rate, which is computed on the full marginal test fold; conformal sets are only actually applied
to gate-negative genomes at inference, so the served-population figure is the operational one.

## Conformal guarantee availability

The finite-sample coverage guarantee needs ≈`ceil(1/α)-1 = 9` calibration points **per class**
(ADR-0004). Only **trimethoprim-sulfamethoxazole** clears it; the other four are
`conformal_guarantee_available = false` — their thresholds still function, but the coverage
guarantee is *unavailable*, and the report says so rather than implying a guarantee it cannot
honour. An α-sensitivity table (α ∈ {0.05, 0.10, 0.20}) is in `results_summary.json`.

## What we do / don't cover — limitations

- **Sample size is small.** 130 genomes / 67 groups; per-drug gate-negative test folds of 10–23
  and unseen-lineage folds of 2–19. Treat all metrics as indicative, not validated performance.
- **Single-class folds.** 3/5 drugs have all-susceptible test folds; their high balanced accuracy
  is trivial and AUROC/PR-AUC are undefined.
- **Gate-negative scope.** Metrics describe only genomes the deterministic gate does not decide.
  Beta-lactam (meropenem/ceftriaxone) resistance is dominated by gate-called carbapenemases/ESBLs,
  so the *model's* gate-negative residual is thin by construction.
- **Conformal guarantee unavailable for 4/5 drugs** (thin calibration folds).
- **Species-locked** to *K. pneumoniae*; no other organism is in scope.
- **Not a clinical device.** Every output requires laboratory confirmation.

## Biases & ethical considerations

- **Sampling bias:** BV-BRC over-represents sequenced epidemic/resistant clones (e.g. ST258,
  ST307), so class balance and lineage coverage are not population-representative.
- **Label noise:** phenotypes come from mixed breakpoint standards (CLSI vs EUCAST — see
  `DATASHEET.md`), which can flip an S/R call for the same MIC.
- **Defensive-only by construction:** the system never proposes a way to *increase* resistance or
  modify an organism; it is analysis and decision-support for treatment selection.

## Reproducing these numbers

With the processed dataset present (see `DATASHEET.md` / `scripts/build_feature_matrix.py`):

```bash
uv run python scripts/run_eval.py --models-dir models   # writes models/eval_summary.json
```

The run exits non-zero and refuses to ship if any drug's re-derived test metrics diverge from
its committed `metrics.json` (`reproducibility.committed_match == false`). For the committed
artifacts here every drug matched exactly (max delta 0.0).
