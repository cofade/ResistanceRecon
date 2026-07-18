# AMRFinderPlus Feature Extraction (Docker/WSL2)

*Transcribed from the 2026-07-18 Genome Firewall design workflow (research agent R2). Web-grounded; sources below.*

## Key findings

- Official Docker image is `ncbi/amr` on Docker Hub; tags are `software_version-database_date.revision` (e.g. `ncbi/amr:4.2.7-2026-05-15.1`). Each image bundles a matching DB build, so a freshly pulled tag needs no `-u`.
- Core run pattern (from `github.com/ncbi/docker/tree/master/amr` README): `docker run --rm -v ${PWD}:/data ncbi/amr amrfinder -n <contigs.fa> -O Klebsiella_pneumoniae --plus --threads 8 -o /data/<sample>.tsv`. `-n` is nucleotide-contigs mode (matches BV-BRC assemblies); `-p`/`-g` are for protein+GFF mode instead.
- `-O`/`--organism Klebsiella_pneumoniae` is one of ~33 curated taxa. It enables: (a) curated point-mutation screening in known resistance-determining loci for that species (chromosomal QRDR loci gyrA/gyrB/parC/parE for fluoroquinolones and other organism-curated point-mutation genes), (b) organism-specific hierarchy/naming resolution, (c) suppression of genes irrelevant to that taxon. Without `-O`, AMRFinderPlus only BLAST/HMM-screens acquired AMR genes and reports zero point mutations.
- `--plus` adds the "Plus" scope: stress-response (acid/biocide/heat/metal), virulence, and AMR-adjacent genes beyond the tightly curated "core" AMR set; the `Scope` column records core vs plus per hit.
- Database update/versioning: `amrfinder -u` (alias `--update`) downloads latest dated DB; `amrfinder -V` reports installed software+DB version; `amrfinder --force_update` re-downloads if partial/broken (known issue in some 4.2.x releases requiring an explicit workaround).
- Reproducibility: two independent pinning mechanisms exist — (1) pin the Docker image tag itself, which fixes both the amrfinder binary and the DB build (cleanest for a hackathon/reproducible pipeline); (2) inside a container, download an explicit dated DB directory from `https://ftp.ncbi.nlm.nih.gov/pathogen/Antimicrobial_resistance/AMRFinderPlus/database/<format_version>/<YYYY-MM-DD.#>/` and pass it via `amrfinder -d <db_dir>`. Record both the image tag and the DB `version.txt` content in run metadata either way.
- Full ordered TSV column list confirmed via the wiki source (protein-mode adds Protein id/start/stop/strand; nucleotide-only mode omits some): **Protein id, Contig id, Start, Stop, Strand, Gene symbol (Element symbol), Sequence name (Element name), Scope, Element type, Element subtype, Class, Subclass, Method, Target length, Reference sequence length, % Coverage of reference, % Identity to reference, Alignment length, Closest reference accession, Closest reference name, HMM accession, HMM description**, and optional **Hierarchy node** (with `--print_node`).
- Element type values: `AMR`, `STRESS`, `VIRULENCE`. Element subtype values: `AMR` → `AMR`, `POINT` (curated resistance mutation), `POINT_DISRUPT` (putatively function-disrupting novel mutation); `STRESS` → `ACID`/`BIOCIDE`/`HEAT`/`METAL`; `VIRULENCE` → `VIRULENCE`/`ANTIGEN`/`STX_TYPE`.
- Method column (confidence/provenance of the call) — see table below. `PARTIAL_CONTIG_END` (50-90% length, at contig edge — often actually full-length, an assembly-fragmentation artifact) is worth flagging separately in QC. Point-mutation calls use `POINT`/`POINTX`/`POINTN` (P=protein-based, X=translated nucleotide, N=nucleotide BLAST).

| Method value | Meaning |
|---|---|
| `ALLELE` | 100% match to a named allele |
| `EXACT` | 100% match, unnamed allele |
| `BLAST` | >90% length & identity |
| `PARTIAL` | 50-90% length, internal to contig |
| `PARTIAL_CONTIG_END` | 50-90% length, at contig edge — often actually full-length, an assembly-fragmentation artifact worth flagging separately in QC |
| `INTERNAL_STOP` | premature stop — likely nonfunctional |
| `HMM` | distant homolog via HMM only |
| `POINT` / `POINTX` / `POINTN` | point-mutation calls (P=protein-based, X=translated nucleotide, N=nucleotide BLAST) |

- Class/Subclass columns give the direct gene(mutation)→drug mapping needed for the "known-mechanism" evidence layer: `Class` is the broad antibiotic family (e.g. `BETA-LACTAM`, `FLUOROQUINOLONE`, `AMINOGLYCOSIDE`), `Subclass` is the specific drug/subfamily (e.g. `CARBAPENEM`, `CEPHALOSPORIN`). These come from NCBI's curated Pathogen Detection Reference Gene Catalog (`ReferenceGeneCatalog.txt`, distributed on the AMRFinderPlus FTP alongside `fam.tab`); this file is the authoritative machine-readable gene-to-class/subclass table and should be pulled directly (pinned to the same DB version as the Docker image) rather than re-derived from TSV output alone, since it also carries genes not observed in your cohort.
- hAMRonization (PHA4GE) is the standard harmonization layer across AMRFinderPlus/ResFinder/RGI/CARD/abricate/etc., mapping each tool's differently-named columns (e.g. AMRFinderPlus `Contig id` vs RGI `Contig` vs ResFinder `contig_name`) into one common schema — useful if a ResFinder or RGI cross-check module is added later, but not needed if AMRFinderPlus remains the sole annotator for the hackathon build.
- No official AMRFinderPlus feature confirms this, but AMRFinderPlus itself only screens genes/loci already in its curated database (acquired AMR genes + curated point-mutation loci); it does not do generic essential-gene completeness/intactness checks outside that curated panel.

## Specific choices

### Exact amrfinder invocation for the pipeline

**Choice:**
```
docker run --rm -v "${PWD}:/data" ncbi/amr:4.2.7-2026-05-15.1 amrfinder -n /data/<sample>.fna -O Klebsiella_pneumoniae --plus --threads 8 --name <sample_id> -o /data/<sample_id>.amrfinder.tsv
```

**Rationale:** `-n` for nucleotide contigs (matches BV-BRC FASTA assemblies, no annotation/GFF step needed); `-O Klebsiella_pneumoniae` turns on curated point-mutation screening (QRDR etc.) which is essential evidence for the ML feature set; `--plus` captures stress/virulence context useful for the RAG evidence layer even though only core AMR scope should feed the regularized-LR baseline by default; `--name` prepends a sample-id column so many per-genome TSVs concatenate cleanly into one cohort table; the image tag is pinned explicitly (not `:latest`) so software+DB version is fixed for the whole hackathon run and recorded in run metadata for reproducibility.

### Feature-matrix construction from many-genome AMRFinderPlus output

**Choice:** Two-table design:

(a) **Gene presence/absence matrix** — concatenate all `--name`-tagged Core-scope AMR TSVs, filter `Element subtype == AMR` (drop POINT/POINT_DISRUPT rows here), pivot Gene symbol × Sample to a binary matrix (1 if any row for that gene/sample passes coverage/identity thresholds, else 0), with `Method` (ALLELE/EXACT/BLAST/PARTIAL/PARTIAL_CONTIG_END/INTERNAL_STOP/HMM) kept as an auxiliary confidence/quality column per cell rather than collapsed away, and near-duplicate/multi-contig hits for the same gene+sample summed/flagged not silently deduplicated;

(b) **Point-mutation feature set** — filter `Element subtype` in `{POINT, POINT_DISRUPT}`, and one-hot encode by (Gene symbol, specific mutation as parsed from Sequence name / mutation nomenclature per the wiki's Point-mutation-nomenclature page) × Sample, again binary, with POINT_DISRUPT mutations kept in a separate flagged column since they are novel/putative rather than literature-curated.

Join both matrices with the `ReferenceGeneCatalog.txt`-derived Class/Subclass map to let the ML layer and the evidence/RAG layer share one lineage of truth for gene→drug-class.

**Rationale:** AMRFinderPlus's own ecosystem script (`michaelwoodworth/AMRFinder_scripts`) validates this exact presence/absence pivot pattern; keeping Method/coverage/identity as auxiliary columns rather than a hard cutoff-then-drop lets the LR baseline or a downstream conformal layer learn to discount PARTIAL/HMM-only calls, which matters for calibration; splitting AMR-gene features from POINT-mutation features avoids conflating two mechanistically different feature types (acquired gene vs. chromosomal target mutation) that likely need different regularization/priors per antibiotic class.

### Molecular-target compatibility gate implementation

**Choice:** Do NOT rely on AMRFinderPlus for general target-presence/intactness screening — it is out of scope for that. Recommended concrete design:

1. For drug classes where the target IS one of AMRFinderPlus's organism-curated point-mutation loci (fluoroquinolones → gyrA/gyrB/parC/parE via `-O Klebsiella_pneumoniae`), reuse the existing POINT/POINT_DISRUPT calls directly as the gate signal (a POINT_DISRUPT or any PARTIAL/INTERNAL_STOP Method flag on that locus in the AMRFinderPlus TSV = target disrupted).
2. For drug-class targets that fall outside AMRFinderPlus's curated point-mutation panel (e.g. PBPs/ftsI for beta-lactams beyond simple presence, murA for fosfomycin, folP/folA for sulfonamides/trimethoprim if not organism-curated), add a small separate BLASTn/tblastn module: curate one reference sequence per target gene from a K. pneumoniae type-strain RefSeq genome (single species commitment makes this a one-time ~5-10 gene panel), run BLAST of that reference against each sample's contigs, and call the target "disrupted/absent" only if coverage falls below a strict threshold (e.g. <80% of reference length) or an internal stop/frameshift is detected relative to the reference reading frame — mirroring AMRFinderPlus's own PARTIAL/INTERNAL_STOP semantics for consistency.
3. Treat this gate as a deterministic override layered ON TOP of (not replacing) the ML score: target-gene essentially-absent/disrupted ⇒ force a LIKELY_TO_FAIL-consistent or high-resistance-confidence output rather than feeding it as just another LR feature, since for drugs whose only mechanism of action is that specific target, an absent/dead target is close to definitionally non-susceptible (bacteriostatic drugs may be an exception, flag those separately in the mapping table).
4. Expect this gate to fire rarely within a single species for essential single-copy targets (gyrA, rpoB, murA, ftsI) since their disruption is usually lethal in a living isolate — so most of its practical value will be as a sanity-check / evidence-corroboration signal (and an assembly-QC signal, since a spurious "target absent" call is more often a fragmented assembly than real biology) rather than a frequently-firing predictor; document this expectation explicitly in the report/limitations section.

**Rationale:** AMRFinderPlus's documented scope is "genes/point mutations already in its curated reference-gene/point-mutation database" — it does not perform generic essential-gene completeness checks, so a true target-presence gate for arbitrary drug targets requires a separate lightweight BLAST module; reusing AMRFinderPlus's own Method-column semantics (PARTIAL/INTERNAL_STOP/coverage-identity thresholds) for that separate module keeps the two evidence layers self-consistent and auditable, which matters for the "confirm with standard lab testing" defensive-disclosure requirement.

## Commands / recipe

```bash
docker pull ncbi/amr:4.2.7-2026-05-15.1
```

```bash
docker run --rm ncbi/amr:4.2.7-2026-05-15.1 amrfinder -V
```

```bash
docker run --rm -v "${PWD}:/data" ncbi/amr:4.2.7-2026-05-15.1 amrfinder -n /data/<sample>.fna -O Klebsiella_pneumoniae --plus --threads 8 --name <sample_id> -o /data/<sample_id>.amrfinder.tsv
```

```bash
# batch loop (WSL2 bash) over all BV-BRC contig FASTAs in ./genomes
for f in genomes/*.fna; do id=$(basename "$f" .fna); docker run --rm -v "$PWD:/data" ncbi/amr:4.2.7-2026-05-15.1 amrfinder -n "/data/genomes/$id.fna" -O Klebsiella_pneumoniae --plus --threads 8 --name "$id" -o "/data/results/$id.amrfinder.tsv"; done
```

```bash
# concatenate per-genome TSVs into one cohort table (headers from --name column let this be a simple tail -n +2 concat)
head -n1 results/$(ls results | head -1) > cohort_amrfinder.tsv; for f in results/*.tsv; do tail -n +2 "$f" >> cohort_amrfinder.tsv; done
```

```bash
# fetch the gene->class/subclass reference table pinned to the same DB version
curl -O https://ftp.ncbi.nlm.nih.gov/pathogen/Antimicrobial_resistance/AMRFinderPlus/database/<format_version>/<YYYY-MM-DD.#>/ReferenceGeneCatalog.txt
```

```bash
# optional explicit DB pin instead of relying purely on image tag
docker run --rm -v "${PWD}:/data" ncbi/amr:4.2.7-2026-05-15.1 amrfinder -n /data/<sample>.fna -O Klebsiella_pneumoniae --plus -d /data/db/<YYYY-MM-DD.#> --threads 8 -o /data/<sample>.amrfinder.tsv
```

## Recommendations

- Pin the exact Docker tag (e.g. `ncbi/amr:4.2.7-2026-05-15.1`) for the whole hackathon and log it plus `amrfinder -V` output and the DB's `version.txt`/`changes.txt` in every run's metadata — this is the cheapest reproducibility win and should be a one-line addition to the pipeline config.
- Run AMRFinderPlus once per genome with `-O Klebsiella_pneumoniae --plus --name <sample_id>`, but build the LR baseline's default feature set from `Scope==core` rows only (optionally ablate with plus-included as a secondary experiment), since core is the curated, phenotype-relevant AMR set.
- Pull `ReferenceGeneCatalog.txt` from the AMRFinderPlus FTP at the same pinned DB version and treat it as the single source of truth for gene→Class/Subclass mapping in both the ML feature-naming layer and the RAG evidence-context layer, rather than re-deriving the mapping ad hoc from the TSVs you happen to observe.
- Build the target-gate BLAST module as a small, separate, well-documented component (own reference FASTA panel, own thresholding, own output table) so it can be cited independently in the report as a deterministic, non-ML, auditable safety layer — this directly supports the project's "defensive decision-support, always recommend lab confirmation" framing.
- Defer ResFinder/RGI/hAMRonization integration to the documented follow-up phase; note in the writeup that hAMRonization is the natural harmonization layer if/when a second annotator (e.g. RGI/CARD for S. aureus mecA/SCCmec context) is added.

## Risks & to-validate

- AMRFinderPlus 4.2.4 had a known bug where `--organism Klebsiella_pneumoniae` failed with an incompletely auto-downloaded database; mitigate by pinning a tag at or after 4.2.5, or running `amrfinder --force_update` once inside the container before the real run and re-verifying `amrfinder -V`.
- `PARTIAL_CONTIG_END` hits are frequently assembly-fragmentation artifacts (a gene split across a contig boundary), not true partial genes — if not filtered/flagged separately, they can corrupt the presence/absence matrix, especially for draft/short-read-derived BV-BRC assemblies; add an explicit QC flag rather than silently treating `PARTIAL_CONTIG_END` the same as `PARTIAL`.
- Class/Subclass fields can be blank for Plus-scope or newly added genes with incomplete curation; the ML/evidence pipeline needs a defined fallback (e.g. `UNMAPPED_CLASS`) rather than crashing or silently dropping such genes.
- The target-presence gate as designed will rarely fire within a single species for essential genes — do not oversell it in the report as a major differentiator; frame it accurately as a rare-but-high-confidence override plus an assembly-QC signal.
- Homology-aware grouped train/test split (already a locked-in decision) must be applied consistently to the presence/absence and point-mutation matrices built here — leakage risk if genomes from the same outbreak clone/clade land on both sides of the split, which is a known failure mode for AMR-gene-based ML on Klebsiella pneumoniae given its clonal population structure.

## Sources

- https://github.com/ncbi/amr
- https://github.com/ncbi/amr/wiki
- https://github.com/ncbi/amr/wiki/Running-AMRFinderPlus
- https://raw.githubusercontent.com/wiki/ncbi/amr/Running-AMRFinderPlus.md
- https://github.com/ncbi/amr/wiki/Interpreting-results
- https://github.com/ncbi/amr/wiki/AMRFinderPlus-database
- https://raw.githubusercontent.com/wiki/ncbi/amr/AMRFinderPlus-database.md
- https://github.com/ncbi/docker/tree/master/amr
- https://hub.docker.com/r/ncbi/amr
- https://github.com/ncbi/amr/issues/25
- https://github.com/ncbi/amr/issues/30
- https://github.com/ncbi/amr/issues/51
- https://github.com/ncbi/amr/issues/19
- https://github.com/michaelwoodworth/AMRFinder_scripts
- https://www.nature.com/articles/s41598-021-91456-0
- https://www.ncbi.nlm.nih.gov/pmc/articles/PMC8208984/
- https://journals.asm.org/doi/10.1128/aac.00483-19
- https://www.biorxiv.org/content/10.1101/2024.03.07.583950v1.full
- https://github.com/pha4ge/hAMRonization
- https://github.com/pha4ge/hAMRonization-workflow
