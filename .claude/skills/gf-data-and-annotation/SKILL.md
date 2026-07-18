---
name: gf-data-and-annotation
description: Runbook for sourcing BV-BRC K. pneumoniae data and running AMRFinderPlus (Docker/WSL2) to build the feature matrix. Offline/dev only — never in CI. Full detail in Documentation/research-findings/.
user_invocable: true
---

# Data & Annotation Runbook

> Full grounding: [`bv-brc-data-access.md`](../../../Documentation/research-findings/bv-brc-data-access.md) and [`amrfinderplus-features.md`](../../../Documentation/research-findings/amrfinderplus-features.md). This skill is the actionable summary. Run everything inside WSL2 Ubuntu.

## 1. BV-BRC labels + genomes (lab-measured AST only)

```bash
# lab AST phenotypes (bulk flat file), then filter to K. pneumoniae + Laboratory Method
wget --ftp-user=anonymous --ftp-password=guest \
  ftps://ftp.bv-brc.org/RELEASE_NOTES/PATRIC_genome_AMR.txt -O PATRIC_genome_AMR.txt
# cross-check counts via the Data API (taxon_id 573 = K. pneumoniae)
curl "https://www.bv-brc.org/api/genome_amr/?and(eq(taxon_id,573),eq(evidence,Laboratory+Method))&facet((field,antibiotic,limit,20),(field,resistant_phenotype))&json(nl,map)&http_accept=application/solr+json"
# download .fna ONLY for label-bearing genome_ids
for i in $(cut -f1 kp_lab_ast_genome_ids.txt); do wget -qN "ftps://ftp.bv-brc.org/genomes/$i/$i.fna" --ftp-user=anonymous --ftp-password=guest; done
```

**Guardrails:** keep only rows with `evidence == 'Laboratory Method'` (never model-generated "general phenotype"). Enumerate all distinct `evidence` values before finalizing the filter. Keep `testing_standard` (CLSI vs EUCAST) as metadata. Group by `genome_id`(+lineage) for the split.

## 2. AMRFinderPlus (pinned Docker)

```bash
docker pull ncbi/amr:4.2.7-2026-05-15.1
docker run --rm ncbi/amr:4.2.7-2026-05-15.1 amrfinder -V          # record binary + DB version
docker run --rm -v "$PWD:/data" ncbi/amr:4.2.7-2026-05-15.1 \
  amrfinder -n /data/<sample>.fna -O Klebsiella_pneumoniae --plus --threads 8 --name <sample_id> \
  -o /data/<sample_id>.amrfinder.tsv
```

**Guardrails:** pin the tag (≥ 4.2.5; 4.2.4 had an `--organism` DB bug). `-O Klebsiella_pneumoniae` enables gyrA/parC point mutations — do not omit it. Flag `PARTIAL_CONTIG_END` hits as QC, not real partial genes. Pull `ReferenceGeneCatalog.txt` at the same DB version for gene→Class/Subclass mapping.

## 3. Feature matrix

Two tables: gene presence/absence (`Element subtype == AMR`) and point mutations (`POINT` / `POINT_DISRUPT`), keeping `Method` as an auxiliary confidence column. Emit a versioned `feature_schema.json` (ordered feature names + pinned DB version hash) alongside every trained model.

## Hard rules

- This runbook is **offline/dev only**. CI never installs or runs Docker/AMRFinderPlus — it uses `MockAnnotator`.
- Re-validate `MockAnnotator` fixtures against a real run periodically (mock/real drift is a documented risk).
