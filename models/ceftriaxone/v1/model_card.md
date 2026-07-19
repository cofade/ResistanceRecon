# Model card -- ceftriaxone (v1)

Per-antibiotic L2 logistic regression + sigmoid calibration + class-conditional (Mondrian) split-conformal. **Decision support only -- confirm every result with standard laboratory antimicrobial susceptibility testing.**

## Provenance
- status: **trained**
- best C: 0.01
- min-n gate: 76 R / 51 S (ok=True)
- homology groups: 66 (backend mlst_st, seed 0); split degraded=False

## Headline metrics (gate-negative test fold -- the population the model serves)
- n: 10 (0 R / 10 S)
- resistant recall: 0.000
- susceptible recall: 1.000
- balanced accuracy: 1.000
- AUROC: n/a | PR-AUC: n/a

## Calibration
- Brier score: 0.149

## Conformal (no-call) behaviour
- alpha: 0.1
- tau_s: 1.000 | tau_r: 1.000
- calibration counts: 8 S / 7 R
- finite-sample guarantee available: **False**

## Top signed coefficients (statistical-association evidence)
- `eng:n_qrdr_mutations`: +0.139
- `eng:has_esbl_or_ampc`: +0.111
- `eng:has_ame`: +0.092
- `eng:has_sul`: +0.073
- `blaOXA-1`: +0.073
- `blaCTX-M-15`: +0.071
- `aac(6')-Ib-cr5`: +0.070
- `catB3`: +0.069
- `blaTEM-1`: +0.064
- `eng:has_dfr`: +0.062
