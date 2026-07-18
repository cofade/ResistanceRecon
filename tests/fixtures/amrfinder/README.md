# AMRFinderPlus fixture TSVs

One file per `genome_id`, matching the real per-genome AMRFinderPlus workflow
(`--name <genome_id> -o <genome_id>.amrfinder.tsv`). Loaded by `MockAnnotator`
(`src/genome_firewall/annotation/mock.py`) via the shared parser in `annotation/_tsv.py`
-- the same parser the real Docker runner uses, so these fixtures exercise the exact
code path production AMRFinderPlus output goes through.

Header and column values are the REAL AMRFinderPlus TSV shape, confirmed against a live
`docker run ncbi/amr:4.2.7-2026-05-15.1` pass against NCBI RefSeq `GCF_000016305.1`
(*Klebsiella pneumoniae* MGH 78578) during EPIC 2 implementation -- see the PR description
for the full run log (image tag, `amrfinder -V`, hit counts).

- **`573.10001.tsv`** -- real rows, taken directly from that live run (renamed `Name`
  column to match the BV-BRC-style genome_id used elsewhere in the fixtures, e.g.
  `tests/fixtures/bvbrc/`). Covers: `Element subtype` AMR/POINT/POINT_DISRUPT; `Method`
  ALLELEX/BLASTX/EXACTX/POINTX/INTERNAL_STOP; `core` and `plus` `Scope`; blank
  Class/Subclass on a `STRESS` row (expected/normal for that type, not a data-quality
  gap); and `blaTEM-1` hit twice at two different loci (a real near-duplicate-gene case).
- **`573.10002.tsv`** -- header only, zero hits. A genome with no AMR/stress/virulence
  calls at all -- exercises the empty-feature-vector path.
- **`573.10003.tsv`** -- hand-synthesized rows for cases the one real run didn't happen
  to produce: a `PARTIAL_CONTIG_ENDX` hit (`blaKPC-3` split at a contig boundary -- a
  realistic scenario for fragmented draft assemblies, not a real AMRFinderPlus call),
  an `HMM`-only hit, an `AMR`-subtype row with blank Class/Subclass that is NOT in
  `ReferenceGeneCatalog.txt` (`newGene-1` -- exercises the `unmapped_class_genes` QC
  flag), and an `AMR`-subtype row with blank Class/Subclass that IS resolvable via the
  catalog (`blaSHV-12` -- its real Class/Subclass, BETA-LACTAM/CEFIDEROCOL-CEPHALOSPORIN,
  is blanked here to simulate a TSV that didn't populate it, so `ReferenceGeneCatalog`
  resolution can actually be exercised end-to-end).
