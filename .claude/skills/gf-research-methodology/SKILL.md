---
name: gf-research-methodology
description: Load when sourcing or validating any bio or ML claim for Genome Firewall — antibiotic mechanisms, resistance genes/mutations, BV-BRC data provenance, calibration/conformal method choices, or literature-backed thresholds — and when deciding whether a finding needs a Documentation/research-findings/ doc. Carries evidence-quality tiers, the KNOWN-vs-STATISTICAL rule, BV-BRC provenance rules, and citation discipline.
user_invocable: true
---

# Genome Firewall — Research Methodology

Every domain and method claim must be traceable to a source, and the strength of the claim must match the strength of the source. This is where the "Ground Truth First" golden rule is operationalized before a line of code encodes it.

## Evidence-quality tiers (strongest → weakest)

1. **Curated authoritative reference** — NCBI AMRFinderPlus reference gene catalog, CARD/ResFinder curated mechanisms, CLSI/EUCAST breakpoints. Use for `KNOWN_MECHANISM`.
2. **Peer-reviewed primary literature** — a specific mechanism/phenotype link with a citation.
3. **Measured data** — BV-BRC lab-AST rows with `evidence == 'Laboratory Method'`.
4. **Model / statistical signal** — an LR coefficient or SHAP value. This is `STATISTICAL_ASSOCIATION`, **never** a proven cause, no matter how strong.

A tier-4 signal may motivate a hypothesis but must not be *documented or displayed* as a mechanism. The `evidence_category` field enforces this at runtime; this skill enforces it at authoring time.

## BV-BRC provenance rules

- Keep only lab-measured AST: `evidence == 'Laboratory Method'`. Discard model-derived / "general phenotype" labels — the challenge warns against them (ADR-0001).
- Record the query, taxon (573), download date, and record counts in the research finding — reproducibility depends on it.
- Respect the per-drug min-n gate (≥ 20 R and ≥ 20 S) before treating a drug as modelable.

## When a claim needs a `research-findings/` doc

Write (or extend) a `Documentation/research-findings/*.md` in the **same session** when you: adopt a new mechanism/gene/mutation into the KB; choose or change a data source; justify a threshold (alpha, ANI, min-n) from literature; or make a bio/ML methodology decision that later code will assume. Pair it with an ADR when it is also an architecture decision (`gf-docs-and-writing`).

## Citation discipline

- Every non-obvious factual claim carries a source (URL, DOI, tool + version, or dataset + date).
- Separate what a source *says* from what you *infer* — label inferences.
- Distinguish "this gene is in the AMRFinderPlus catalog for this drug class" (tier 1) from "this gene correlated with resistance in our data" (tier 3/4). They are different claims with different UI wording.
- When two sources conflict, record both and the resolution — do not silently pick one.

## When NOT to use this skill

- Proving a threshold/statistical method or a third-party tool's behavior with a runnable experiment → `gf-proof-and-analysis`.
- Where the finding gets recorded / house style → `gf-docs-and-writing`.
- The runtime KNOWN-vs-STATISTICAL contract → `gf-architecture-contract`.
