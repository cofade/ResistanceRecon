# Model card -- gentamicin (v1)

Per-antibiotic L2 logistic regression + sigmoid calibration + class-conditional (Mondrian) split-conformal. **Decision support only -- confirm every result with standard laboratory antimicrobial susceptibility testing.**

## Provenance
- status: **trained**
- best C: 10.0
- min-n gate: 48 R / 73 S (ok=True)
- homology groups: 65 (backend mlst_st, seed 0); split degraded=False

## Headline metrics (gate-negative test fold -- the population the model serves)
- n: 18 (4 R / 14 S)
- resistant recall: 0.500
- susceptible recall: 0.929
- balanced accuracy: 0.714
- AUROC: 0.875 | PR-AUC: 0.761

## Calibration
- Brier score: 0.112

## Conformal (no-call) behaviour
- alpha: 0.1
- tau_s: 0.547 | tau_r: 1.000
- calibration counts: 9 S / 4 R
- finite-sample guarantee available: **False**

## Top signed coefficients (statistical-association evidence)
- `aac(3)-IIe`: +2.980
- `eng:has_ame`: +2.222
- `aac(6')-Ib'`: +2.167
- `ant(2'')-Ia`: +1.397
- `aadA1`: +1.301
- `dfrA12`: -1.259
- `qnrB1`: +1.180
- `blaOXA-9`: -1.142
- `eng:has_carbapenemase`: +1.108
- `aac(3)-IId`: +1.102
