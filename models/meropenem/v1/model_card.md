# Model card -- meropenem (v1)

Per-antibiotic L2 logistic regression + sigmoid calibration + class-conditional (Mondrian) split-conformal. **Decision support only -- confirm every result with standard laboratory antimicrobial susceptibility testing.**

## Provenance
- status: **trained**
- best C: 1.0
- min-n gate: 40 R / 88 S (ok=True)
- homology groups: 67 (backend mlst_st, seed 0); split degraded=False

## Headline metrics (gate-negative test fold -- the population the model serves)
- n: 23 (1 R / 22 S)
- resistant recall: 0.000
- susceptible recall: 1.000
- balanced accuracy: 0.500
- AUROC: 0.045 | PR-AUC: 0.045

## Calibration
- Brier score: 0.096

## Conformal (no-call) behaviour
- alpha: 0.1
- tau_s: 0.352 | tau_r: 1.000
- calibration counts: 13 S / 3 R
- finite-sample guarantee available: **False**

## Top signed coefficients (statistical-association evidence)
- `eng:has_carbapenemase`: +1.493
- `blaKPC-2`: +0.920
- `eng:has_rmtase`: +0.592
- `ble`: +0.572
- `sul1`: +0.520
- `blaOXA`: +0.502
- `eng:has_esbl_or_ampc`: +0.455
- `arr-3`: +0.449
- `blaNDM-1`: +0.445
- `eng:porin_disrupted`: +0.387
