---
name: gf-proof-and-analysis
description: Load before adopting any threshold, statistical method, or third-party tool behavior in Genome Firewall on faith — alpha, per-drug min-n, ANI cutoff, calibration/conformal choice, or what AMRFinderPlus actually emits. Prove it with a small runnable experiment and cite the run; never ship a "vibes" number. Carries the prove-before-adopt workflow and the specific claims that must be proven, not assumed.
user_invocable: true
---

# Genome Firewall — Proof & Analysis

Thresholds and third-party behaviors are load-bearing: a wrong alpha, ANI cutoff, or misread AMRFinderPlus column silently corrupts every downstream verdict. This skill exists so those values are *proven*, not guessed. The discipline is measurement, not theory (it complements `debug-verbose`, which is for bugs).

## Prove-before-adopt workflow

1. **State the claim precisely.** "alpha=0.10 gives ~90% marginal coverage on our calibration fold", not "0.10 seems fine".
2. **Design the smallest experiment** that could falsify it — a script, a fixture run, a query against real tool output.
3. **Run it and capture the evidence** — numbers, the exact command, the tool + version. Save it where it can be cited (a `research-findings/` note or the ADR's Consequences).
4. **Decide from the evidence**, and record the decision in `ground-truth/decisions.jsonl` + an ADR if it's an architecture choice.
5. **Pin it** with a test where feasible, so drift is caught later.

## Claims that must be proven, not assumed

- **Conformal alpha (default 0.10):** verify empirical coverage on a grouped (leakage-free) fold and record the sensitivity table. Coverage is a *guarantee only under the exchangeability assumption* — state where it may not hold.
- **Per-drug min-n gate (≥ 20 R / ≥ 20 S):** justify from the calibration-stability literature/data, not habit.
- **Homology split ANI cutoff (99.5%) and MLST-primary/Mash-fallback:** show that groups don't span train/test on the actual data; the no-leakage test is the proof.
- **Calibration method (sigmoid vs isotonic, `cv='prefit'`):** show sigmoid is the safer choice at the small per-drug fold sizes actually present.
- **AMRFinderPlus behavior:** prove, against a real pinned-image run, which columns/flags you depend on (e.g. `--organism Klebsiella_pneumoniae` enabling QRDR point mutations; `PARTIAL_CONTIG_END` artifacts). Do **not** infer tool output shape from docs alone — `gf-data-and-annotation` covers the pinned image; never run it in CI.
- **The MockAnnotator fixtures** faithfully represent real output — re-validate periodically against a real run.

## Anti-patterns (do not do)

- Shipping a threshold because "it's the sklearn default" or "the paper used it" without checking it on *our* data.
- Reporting conformal coverage from an ungrouped split (leakage inflates it).
- Trusting a third-party column's meaning without seeing a real row.
- Presenting a single run as a stable estimate when variance matters — say so, or repeat it.

## When NOT to use this skill

- Debugging a concrete misbehavior → `debug-verbose`.
- Sourcing a mechanism/literature claim (not a runnable number) → `gf-research-methodology`.
- What evidence a PR needs overall → `gf-validation-and-qa`.
