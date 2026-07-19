# ADR-0018 — Deterministic gate semantics: one-directional (resistance-only)

- **Date:** 2026-07-19
- **Status:** Accepted
- **Origin:** Agent-proposed / human-approved via the challenge brief (EPIC 3 planning session, issue #19). **Safety-critical.**

## Context

The challenge brief requires a deterministic molecular-target gate and is explicit that the system must "account for the presence of the drug's molecular target, so [it] does not report 'likely to work' based solely on the absence of resistance markers." A carbapenemase-negative genotype does not guarantee susceptibility (the porin-loss route). The open question was whether the gate may also FORCE a `likely_to_work` verdict.

## Decision

The gate is **ONE-DIRECTIONAL**: `predictor/target_gate.evaluate_gate` only ever forces `likely_to_fail` (on a called known resistance mechanism) and **never** forces `likely_to_work`. Susceptibility is concluded only by the calibrated model + conformal (which can also no-call). The gate records `target_present` (True for every panel drug — PBPs / gyrase-topoisomerase-IV / 30S rRNA / DHFR-DHPS are essential, universally-present targets in K. pneumoniae); a gate hit carries `evidence_category=known_mechanism` and fixed `KNOWN_MECHANISM_CONFIDENCE=0.99`.

Per-drug firing (from `antibiotic-panel.md`): meropenem = any carbapenemase (Subclass=CARBAPENEM); ceftriaxone = ESBL/AmpC or carbapenemase (Subclass CEPHALOSPORIN or CARBAPENEM); ciprofloxacin = ≥2 QRDR mutations OR (≥1 QRDR AND a PMQR gene); gentamicin = a 16S RMTase (AME-only does **not** fire); TMP-SMX = sul or dfrA. Beta-lactam tiers use AMRFinderPlus's Subclass so a narrow blaSHV-1/blaSHV-11 (Subclass=BETA-LACTAM) never fires.

## Consequences

- (+) Structurally impossible to emit a confident-but-wrong "likely to work" from marker-absence — the exact weak-submission failure the brief warns against.
- (+) Combination thresholds for fluoroquinolones/aminoglycosides match the literature (a single determinant ≠ high-level resistance).
- (−) The gate under-fires when a resistance mechanism is present but absent from the pinned AMRFinderPlus DB, or when Subclass is unmapped — accepted; the model + conformal still cover those genomes.
- Pinned by `tests/predictor/test_target_gate.py` (gate authority + the one-directional property across all panel drugs).
