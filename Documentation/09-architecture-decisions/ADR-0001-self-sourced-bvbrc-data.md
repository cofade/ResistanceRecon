# ADR-0001 — Self-source laboratory AST data from BV-BRC

- **Date:** 2026-07-18
- **Status:** Accepted
- **Origin:** Human (confirmed by challenge organizer: no fixed dataset; "feel free to use any").

## Context

No organizer dataset was provided. The challenge names BV-BRC (formerly PATRIC) as the primary source: 15,000+ genomes linked to lab results. It explicitly warns to use *laboratory-measured* results, NOT general phenotype fields that may contain model-generated predictions.

## Decision

Self-source from BV-BRC. Use the bulk `RELEASE_NOTES/PATRIC_genome_AMR.txt` flat file (FTPS) as the primary AST source, cross-checked via the Data API (`genome_amr`, `eq(taxon_id,573)`). **Filter strictly to `evidence == 'Laboratory Method'`** (equivalently: non-empty `laboratory_typing_method`; exclude `Computational Method`). Target label = `resistant_phenotype` (SIR). Retain `testing_standard`/`laboratory_typing_method` as provenance metadata. Group by `genome_id`(+lineage) for splitting.

## Consequences

- (+) Genuine wet-lab ground truth; ~85k K. pneumoniae lab-AST rows available; carbapenems, cephalosporins, TMP-SMX well-covered.
- (−) Sparse per-drug after grouping; class imbalance and mixed breakpoint standards (CLSI vs EUCAST) must be tracked.
- **To-validate:** FTPS reachability + exact filename; enumerate all distinct `evidence` values before finalizing the filter. Detail: [research-findings/bv-brc-data-access.md](../research-findings/bv-brc-data-access.md).
