# Model card -- ciprofloxacin (v1)

Per-antibiotic L2 logistic regression + sigmoid calibration + class-conditional (Mondrian) split-conformal. **Decision support only -- confirm every result with standard laboratory antimicrobial susceptibility testing.**

## Provenance
- status: **trained**
- best C: 100.0
- min-n gate: 67 R / 59 S (ok=True)
- homology groups: 66 (backend mlst_st, seed 0); split degraded=False

## Headline metrics (gate-negative test fold -- the population the model serves)
- n: 10 (0 R / 10 S)
- resistant recall: 0.000
- susceptible recall: 1.000
- balanced accuracy: 1.000
- AUROC: n/a | PR-AUC: n/a

## Calibration
- Brier score: 0.007

## Conformal (no-call) behaviour
- alpha: 0.1
- tau_s: 1.000 | tau_r: 0.102
- calibration counts: 8 S / 19 R
- finite-sample guarantee available: **False**

## Top signed coefficients (statistical-association evidence)
- `qnrS1`: +3.090
- `eng:n_qrdr_mutations`: +3.062
- `ant(2'')-Ia`: +2.931
- `eng:has_ame`: +2.753
- `qnrB1`: +2.249
- `tet(A)`: +2.124
- `blaSHV-7`: +1.710
- `blaSHV-30`: -1.649
- `blaCTX-M-15`: +1.607
- `ompK35_E132K`: -1.574
