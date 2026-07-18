# ML Methodology — Logistic Regression, Calibration, Conformal No-Call, Grouped Split, Metrics

*Transcribed from the 2026-07-18 Genome Firewall design workflow (research agent R3). Web-grounded; sources below.*

## Key findings

- sklearn `LogisticRegression(class_weight='balanced')` reweights the loss inversely to class frequency (`n_samples/(n_classes*bincount)`); it is the standard, dependency-free way to handle imbalance without oversampling and keeps clean probabilistic outputs needed for downstream calibration/conformal steps.
- L2 (Ridge) regularization is preferable to L1 here: AMR genes frequently co-occur (same plasmid/operon), and L1 arbitrarily zeroes one of several correlated markers, destabilizing coefficients under small-n resampling; L2 stays well-posed even when gene count approaches/exceeds isolate count and mitigates quasi-complete separation from near-perfect single markers (e.g. blaKPC for carbapenems).
- Per-drug (independent binary) models beat a joint multilabel model because: different antibiotics have different resistance mechanisms/prevalence; BV-BRC susceptibility testing is not uniform across drugs per isolate so the label matrix is sparse/MNAR and per-drug fitting naturally uses only isolates labeled for that drug; sklearn's own multilabel wrappers for LR already fit independent per-label estimators internally so a joint model buys little; and per-drug models allow independent calibration, independent conformal alpha, and independent per-gene evidence per drug as the report requires.
- sklearn docs: isotonic calibration overfits when the calibration set is small (rule of thumb well under ~1000 samples); sigmoid (Platt, 2 parameters) is preferred for small/imbalanced data and for classifiers biased toward the majority class. Per-drug calibration sets here will likely be tens-to-low-hundreds of isolates, so sigmoid should be the default, with isotonic as an opt-in for the rare high-n, high-prevalence drug.
- `CalibratedClassifierCV`'s own internal cv splitting is NOT group-aware, so using it naively after a homology-aware split can still leak near-duplicate genomes into the calibration fold; safest pattern is to build the grouped train/calibration/test partition yourself (via `StratifiedGroupKFold`) and pass `cv='prefit'` to `CalibratedClassifierCV`, calibrating only on the explicitly held-out grouped calibration fold.
- Nested CV rationale: outer grouped split gives unbiased performance metrics; inner grouped split is used for C selection and calibration fitting; calibrating or tuning on the same data used for outer-test metrics inflates Brier/AUROC. Full nested CV is time-expensive; a defensible hackathon simplification is one outer grouped train/test split plus an inner grouped k-fold for tuning/calibration, documented explicitly as a scoped-down version of full nested CV.
- MAPIE (scikit-learn-contrib) offers LAC, APS, Top-K, RAPS conformity scores via a newer `SplitConformalClassifier` API (v1.x); LAC is known to produce empty prediction sets when the model is very uncertain at the decision boundary — which is exactly the "novel/no-call" behavior this product wants, not a bug to work around.
- crepes (Henrik Bostrom) implements Mondrian conformal classifiers via a `MondrianCategorizer` passed to `calibrate()`, giving class- or group-conditional coverage rather than only marginal coverage — directly usable to guarantee per-genetic-cluster (e.g. per-ST) coverage, which ties the conformal layer to the same homology grouping used for the train/test split.
- Binary split-conformal prediction sets over {S,R} map cleanly to product states: `{S}` only -> LIKELY TO WORK, `{R}` only -> LIKELY TO FAIL, `{S,R}` both -> NO-CALL (ambiguous, e.g. borderline/heteroresistance-like genotype), `{}` empty -> NO-CALL (novel, out-of-distribution gene combination unlike anything in the calibration set) — the empty-set case is the formal, guarantee-backed version of "flag genomes unlike anything we trained on."
- Conformal calibration-set-size matters: stable quantiles at significance level alpha need roughly `n_cal >= 1/alpha - 1` per class as an absolute floor, but realistically 50+ per class for a usable quantile; drugs below this floor should be marked "insufficient data for conformal guarantee" rather than given a spuriously narrow set.
- The PLOS Computational Biology tutorial paper on genomic AMR prediction (Libbrecht et al. style tutorial, journal.pcbi.1012579) explicitly recommends MLST-blocked cross-validation for this exact task, reports that blocked CV scores are consistently lower than random k-fold (evidence that population structure was previously leaking through naive splits), and flags that under class imbalance overall accuracy can look high while resistance recall collapses (their piperacillin-tazobactam example: high accuracy, ~10% resistance recall) — directly motivating resistant-class recall as a headline metric, not just accuracy.
- Mash distance <=0.05 corresponds to ANI >=95% (classic species boundary); a tighter, better-justified threshold for near-clonal grouping is ANI ~99.5% (Mash distance ~0.005), based on a documented ANI discontinuity/gap between 99.2% and 99.8% in most bacterial species (mBio "ANI gap" paper) that aligns with how sequence types have historically been defined — this is a citable, non-arbitrary threshold for single-linkage clustering into "genetic groups" for splitting.
- skani is reported (Nature Methods 2023, and downstream comparisons) to be faster and more accurate than Mash+FastANI specifically in the high-ANI (>82%), highly-similar-genome, all-to-all regime — which is exactly the regime of comparing K. pneumoniae isolates to each other — making it the technically superior choice over Mash if compute/time budget allows.
- sklearn `StratifiedGroupKFold` preserves per-class proportions across folds subject to the non-overlapping-group constraint, but degrades toward plain `GroupKFold` behavior when a small number of large groups dominate (expected here: a single large resistant clone such as ST258/ST512 could itself contain a large fraction of all resistant isolates) — this must be checked and reported per fold, not assumed away.
- Brier score decomposes into reliability+resolution+uncertainty and is computed via `sklearn.metrics.brier_score_loss`; reliability diagrams are produced via `sklearn.calibration.CalibrationDisplay` (`from_estimator`/`from_predictions`) and should use few bins (5-10) given small per-drug n to avoid empty/noisy bins.
- The product's "no-call vs accuracy-on-called" pair is a selective-classification / risk-coverage framing: reporting e.g. "committed on 65% of isolates at 96% accuracy" is more honest and more clinically useful for a defensive decision-support tool than a single blended accuracy number, and it is exactly what varying the conformal alpha controls (a risk-coverage curve).

## Specific choices

### Calibration method

**Choice:** sklearn `CalibratedClassifierCV` with `method='sigmoid'` (Platt scaling) as the default for every drug; `method='isotonic'` only as an opt-in for a drug whose grouped calibration fold is large (rule of thumb: >=300-1000 samples with >=30-50 per class) and shows a clearly non-sigmoidal miscalibration pattern on the reliability diagram. Fit with `cv='prefit'` against a homology-grouped calibration fold that you construct yourself, not `CalibratedClassifierCV`'s internal (non-group-aware) cv.

**Rationale:** sklearn's own documentation warns isotonic overfits well below ~1000 calibration samples, and per-drug BV-BRC subsets in a 24h hackathon will rarely clear that bar; sigmoid's 2-parameter fit is also specifically recommended for imbalanced, under-confident classifiers. Using `cv='prefit'` on a grouped calibration fold avoids the leakage risk of `CalibratedClassifierCV`'s default internal splitter, which knows nothing about genome homology groups.

### Conformal prediction library

**Choice:** crepes as the primary library (its Mondrian conformal classifier with `MondrianCategorizer` gives class- and/or genetic-group-conditional coverage), with MAPIE's `SplitConformalClassifier` (LAC method) kept as a secondary/cross-check pipeline given its maturity and scikit-learn-contrib status.

**Rationale:** The Mondrian capability in crepes lets the coverage guarantee be conditioned on the same genetic clusters/STs used for the train/test split, directly reinforcing the homology-aware story rather than only offering marginal (whole-population-averaged) coverage that a dominant clone could dominate. MAPIE is kept alongside because it is more battle-tested, offers more conformity-score options (APS, Top-K, RAPS) as a fallback, and is worth a sanity-check comparison given the time budget allows a second, independent implementation of the same guarantee.

### Clustering / grouped-split method

**Choice:** Primary group id = MLST sequence type (pulled directly from BV-BRC metadata where available, zero extra compute). Fallback/cross-check for isolates missing ST, or to catch cross-ST near-duplicates = Mash-distance single-linkage clustering at distance ~0.005 (~ANI 99.5%). skani noted as a higher-accuracy alternative to Mash if time permits. Splitting done with sklearn `StratifiedGroupKFold(groups=cluster_id, y=resistance_label)`, plus an explicit leave-one-group-out check holding out >=1 entire ST/cluster never seen in training.

**Rationale:** MLST is the field-standard epidemiological grouping for K. pneumoniae, is explicitly recommended for this exact ML task by the PLOS Comp Biol AMR-ML tutorial paper (which also shows blocked CV scores are meaningfully lower than naive random k-fold), and costs nothing extra to compute if BV-BRC already reports it. The Mash/ANI-99.5% fallback is included because MLST alone can miss near-identical genomes at ST boundaries or isolates with no assigned ST, and 99.5% ANI is a defensible, cited threshold (documented ANI discontinuity between 99.2-99.8%) rather than an arbitrary pick.

### Metric set reported per drug

**Choice:** Balanced accuracy, resistant-class recall (headline), susceptible-class recall, F1, AUROC, PR-AUC, Brier score, reliability diagram, and the selective-prediction pair no-call rate + accuracy-on-called — each reported (a) marginally over the full grouped test set, (b) broken out per genetic group/ST, and (c) specifically on the held-out unseen-lineage group.

**Rationale:** Accuracy alone is misleading under imbalance (the tutorial paper's own piperacillin-tazobactam example: high accuracy, ~10% resistance recall), so resistant recall is elevated to headline status since a missed-resistance false call (LIKELY TO WORK when actually resistant) is the clinically dangerous failure mode. PR-AUC is added because AUROC alone can look strong despite poor minority-class separation. No-call rate + accuracy-on-called operationalizes the product's core safety promise (defensive, always-confirm-in-lab) as a measurable risk-coverage tradeoff, and per-group/unseen-lineage breakdowns are what actually demonstrate (or falsify) generalization claims rather than a single aggregate number.

## Recommended pipeline

Implement the pipeline in this order per drug:

1. Filter to isolates with a valid AST label for that drug.
2. Build genetic group ids (MLST ST, fallback Mash single-linkage @ ~99.5% ANI).
3. Outer `StratifiedGroupKFold` (or one outer grouped train/test split given the time budget) using those group ids.
4. Inner grouped split of the outer-training data into model-train and calibration folds.
5. `LogisticRegression(penalty='l2', class_weight='balanced', solver='lbfgs', max_iter=2000)` with C chosen by inner grouped CV grid search.
6. `CalibratedClassifierCV(method='sigmoid', cv='prefit')` fit on the held-out inner calibration fold.
7. crepes Mondrian conformal classifier (categorized by predicted class and/or genetic group) fit on the same or a further calibration split, at a chosen alpha.
8. Evaluate once, untouched, on the outer test fold plus the explicit unseen-lineage holdout.

Additional recommendations:

- Set a minimum-n gate per drug before modeling at all (e.g. require >=20 resistant AND >=20 susceptible isolates after the grouped split, with enough left over for a calibration fold): drugs failing the gate should be marked out of scope / "insufficient data" in the report rather than silently producing an unreliable model, which fits the project's defensive-by-design framing.
- Default alpha=0.10 (90% marginal/group-conditional coverage) with a documented sensitivity table across alpha in {0.05, 0.10, 0.20} showing coverage vs no-call-rate, so the choice is defensible and demoable rather than arbitrary; err toward the more conservative (lower alpha, higher coverage, more no-calls) end given the "always confirm with lab testing" positioning.
- Always report the calibrated probability and the conformal prediction set together in the output: the probability answers "how confident", the conformal set answers "is this confidence backed by a formal coverage guarantee, and should we abstain" — keep both surfaced in the report generator rather than collapsing to one number.
- For the write-up, explicitly label the single outer grouped split (rather than full nested CV) as a documented hackathon-time simplification, with true nested/repeated grouped CV listed as a near-term follow-on to get variance estimates on all metrics.

## Risks & to-validate

- `StratifiedGroupKFold` can silently degrade to plain `GroupKFold` when one or two STs/clusters contain a large fraction of all resistant isolates (very plausible for a well-known carbapenem-resistant clone like ST258/ST512 in K. pneumoniae); if unchecked, a fold could end up with almost no resistant isolates in either train or test, invalidating both training and the reported recall numbers — must inspect and report actual per-fold class balance, not assume it.
- MAPIE's LAC method producing empty sets is desirable conceptually but its exact rate depends heavily on how well-calibrated the underlying probability is; if the calibration step is skipped or done on a leaking (non-grouped) fold, the empty-set/full-set rates will not reflect genuine novelty/ambiguity and the no-call mechanism loses its statistical meaning.
- Per-drug calibration and conformal calibration sets may be too small (tens of isolates) to give crepes/MAPIE stable quantiles even after gating on minimum-n; document the effective minimum n_cal needed for the chosen alpha (~1/alpha - 1 as an absolute floor, more realistically several times that) and be prepared to report some drugs as "model built, conformal guarantee not available" distinct from "no-call on this genome."
- MLST ST as the primary grouping variable assumes BV-BRC metadata ST assignments are complete and correct for the pulled genome set; any isolates with missing/inconsistent ST need the Mash-fallback clustering step to actually run, or they risk being placed as their own singleton group (which is safe but shrinks effective group-based stratification power) or, worse, silently merged incorrectly with unrelated isolates.
- Sigmoid calibration, while safer for small n, still assumes a monotonic single-parameter-family miscalibration shape; if a drug's uncalibrated LR scores are non-monotonically miscalibrated (e.g. due to strong outlier features), sigmoid calibration will not fix it and the reliability diagram must be inspected per drug rather than trusting the Brier score alone.

## Sources

- https://scikit-learn.org/stable/modules/calibration.html
- https://scikit-learn.org/stable/modules/generated/sklearn.calibration.CalibratedClassifierCV.html
- https://machinelearningmastery.com/probability-calibration-for-imbalanced-classification/
- https://scikit-learn.org/stable/auto_examples/calibration/plot_calibration_curve.html
- https://mapie.readthedocs.io/en/latest/theoretical_description_classification.html
- https://mapie.readthedocs.io/en/stable/v1_release_notes.html
- https://github.com/scikit-learn-contrib/MAPIE
- https://github.com/henrikbostrom/crepes
- https://proceedings.mlr.press/v230/bostrom24a.html
- https://pypi.org/project/crepes/
- https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.StratifiedGroupKFold.html
- https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.GroupKFold.html
- https://www.nature.com/articles/s41592-023-02018-3
- https://journals.asm.org/doi/10.1128/mbio.02696-23
- https://www.nature.com/articles/s41467-018-07641-9
- https://pmc.ncbi.nlm.nih.gov/articles/PMC4915045/
- https://journals.plos.org/ploscompbiol/article?id=10.1371%2Fjournal.pcbi.1012579
- https://pmc.ncbi.nlm.nih.gov/articles/PMC9309105/
