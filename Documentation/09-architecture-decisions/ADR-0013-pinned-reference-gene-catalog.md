# ADR-0013 — Commit a pinned copy of NCBI's ReferenceGeneCatalog.txt

- **Date:** 2026-07-19
- **Status:** Accepted
- **Origin:** Agent-proposed / human-approved (EPIC 2 planning session, issue #17).

## Context

`reader/feature_builder.py`'s gene presence/absence table needs a Class/Subclass (drug-family)
for every AMR-subtype gene it pivots. Most AMRFinderPlus hits already carry Class/Subclass
directly in the TSV output, but Plus-scope or newly-curated genes can leave it blank. NCBI
publishes `ReferenceGeneCatalog.txt` — the authoritative gene→Class/Subclass table — on the
AMRFinderPlus FTP, pinned per database build
(`https://ftp.ncbi.nlm.nih.gov/pathogen/Antimicrobial_resistance/AMRFinderPlus/database/<format_version>/<db_version>/ReferenceGeneCatalog.txt`).
Confirmed reachable and 2.3MB at the pinned DB version (`4.2/2026-05-15.1`) this session.

Inspecting the real file (not just the pre-implementation research summary) surfaced two
facts that shaped the design: (1) its `allele` column matches AMRFinderPlus's `Element symbol`
directly for named alleles and point mutations (e.g. `blaTEM-1`, `gyrA_S83Y`); genes without
allele-level naming instead match on `gene_family` (e.g. `fieF`) — both keys are needed. (2)
STRESS-type genes (e.g. `fieF`) have blank Class/Subclass in the catalog itself, not just in
TSV output — that is normal/expected for that element type, not a data-quality gap the catalog
fixes, so the fallback only ever applies to `Element subtype == AMR` rows.

## Decision

Commit a pinned copy at `data/reference/ReferenceGeneCatalog.txt` (2.3MB, small enough to treat
like the project's other committed fixture data) rather than fetching it at build/run time.
`reader/feature_builder.ReferenceGeneCatalog` loads it and is consulted only when an AMR-subtype
hit's own `drug_class` is `None`, falling back to `allele` then `gene_family` lookup, then to
leaving the gene in `GenomeFeatureVector.unmapped_class_genes` if still unresolved.

## Consequences

- (+) No network dependency at feature-build time; reproducible without re-fetching from NCBI.
- (+) Same commit-small-reference-data pattern already used for `tests/fixtures/`, so no new
  convention to learn.
- (−) The catalog is now a second pin (alongside the Docker image tag) that must be updated
  together if the AMRFinderPlus DB version ever moves — both live at the same `2026-05-15.1`
  value today; a version mismatch between them is a latent drift risk, not currently checked
  automatically. Revisit if/when the DB version is bumped.
- **Alternative considered:** fetch it via a script into `data/raw/` (gitignored), matching the
  BV-BRC data pattern. Rejected for EPIC 2 — 2.3MB is small enough that committing it is simpler
  and removes a network dependency from a step that otherwise has none (unlike the multi-GB BV-BRC
  pull, which genuinely needs to stay out of git).
