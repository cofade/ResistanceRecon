# Model card -- trimethoprim-sulfamethoxazole (v1)

Per-antibiotic L2 logistic regression + sigmoid calibration + class-conditional (Mondrian) split-conformal. **Decision support only -- confirm every result with standard laboratory antimicrobial susceptibility testing.**

## Provenance
- status: **trained**
- best C: 10.0
- min-n gate: 62 R / 67 S (ok=True)
- homology groups: 66 (backend mlst_st, seed 0); split degraded=False

## Headline metrics (gate-negative test fold -- the population the model serves)
- n: 10 (0 R / 10 S)
- resistant recall: 0.000
- susceptible recall: 1.000
- balanced accuracy: 1.000
- AUROC: n/a | PR-AUC: n/a

## Calibration
- Brier score: 0.089

## Conformal (no-call) behaviour
- alpha: 0.1
- tau_s: 0.702 | tau_r: 0.506
- calibration counts: 12 S / 9 R
- finite-sample guarantee available: **True**

## Top signed coefficients (statistical-association evidence)
- `eng:has_dfr`: +2.273
- `eng:has_sul`: +1.840
- `sul1`: +1.809
- `catA1`: +1.703
- `blaKPC-2`: -1.521
- `blaCTX-M-15`: +1.030
- `eng:has_esbl_or_ampc`: +0.969
- `aph(3'')-Ib`: +0.903
- `aph(6)-Id`: +0.903
- `aadA1`: +0.886
