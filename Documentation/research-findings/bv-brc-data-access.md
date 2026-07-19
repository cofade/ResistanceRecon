# BV-BRC Data Access — K. pneumoniae Genomes + Laboratory AST Labels

*Transcribed from the 2026-07-18 Genome Firewall design workflow (research agent R1). Web-grounded; sources cited below. Items marked to-validate must be confirmed against a live client before being relied upon.*

## Key findings

- FTP: host `ftp.bv-brc.org`, FTPS required (plain FTP no longer works). Anonymous login user=`anonymous` pass=`guest`. Per-genome files live at `ftps://ftp.bv-brc.org/genomes/<genome_id>/<genome_id>.<ext>` with extensions `.fna` (contig FASTA), `.faa` (protein), `.ffn`/`.frn`, `.features.tab`, `.gff`, `.spgene.tab` (specialty/AMR genes), `.subsystem.tab`, `.pathway.tab`.

- FTP bulk metadata lives under `ftps://ftp.bv-brc.org/RELEASE_NOTES/`: `genome_summary`, `genome_metadata`, `genome_lineage` (tab-delimited, all public genomes), and `PATRIC_genome_AMR.txt` which is the bulk laboratory AMR phenotype table for ALL genomes in one tab-delimited file — the best bulk AST source, avoiding per-genome API calls. **To-validate:** this specific file host is behind Globus/HTTPS proxying now; the connect attempt to `ftp.bv-brc.org` over plain HTTPS from this sandbox was refused, so verify exact filename/availability with a real FTPS client such as `lftp` or `wget --ftp-user` before relying on it. **Update (issue #41, 2026-07):** confirmed live — the singular/plural ambiguity flagged below was real and the server-side name has since drifted to the plural `PATRIC_genomes_AMR.txt`. `scripts/fetch_bvbrc_data.py` no longer pins one spelling: `ftps_download_flatfile()` tries every name in `KNOWN_FLATFILE_NAMES` (plural first) and falls back on a clean `550`, so this is a resolved risk, not an open one — see Documentation/11-risks-and-technical-debt/README.md §11.4 for the incident.

- Data API base: `https://www.bv-brc.org/api/<collection>/` built on Apache Solr (38 collections). Supports RQL (`eq(field,value)`, `and(...)`, `facet((field,x,limit,N))`, `select(...)`, `rows(N)`) and native Solr query syntax. Set header/param `http_accept=application/json` for a simplified single/multi-record JSON, or `application/solr+json` for the full Solr envelope with `numFound` and `facet_counts`. Relevant collections: `genome`, `genome_feature`, `genome_amr`, `genome_sp_gene`, `taxonomy`.

- Confirmed live `genome_amr` record schema by fetching real records: `id`, `owner`, `genome_id`, `genome_name`, `taxon_id`, `antibiotic`, `resistant_phenotype`, `evidence`, `public`, `date_inserted`, `date_modified`.

  | Condition (`evidence` value) | Additional populated fields |
  |---|---|
  | `Laboratory Method` | `laboratory_typing_method` (e.g. 'Broth dilution'), `laboratory_typing_platform` (e.g. 'VITEK 2'), `vendor` (e.g. 'BioMerieux'), `testing_standard` (e.g. 'EUCAST'), `testing_standard_year`, `measurement`, `measurement_value`, `measurement_sign`, `measurement_unit` (e.g. 'mg/L'), `pmid`, `source` |
  | `Computational Method` | `computational_method` (e.g. 'AdaBoost Classifier'), `computational_method_performance` (e.g. 'Accuracy:0.931, F1 score:0.935, AUC:0.950') — and the lab-specific fields (`laboratory_typing_method`, `testing_standard`, `measurement`) are simply absent/empty |

- The decisive lab-vs-predicted discriminator is the `evidence` field. The BV-BRC AMR Metadata doc describes four evidence values overall: `Phenotype` (derived from source metadata/publications, not a formal panel), `AMR Panel` (formal susceptibility panel with SIR or MIC), `Computational Prediction` (ML classifier output), and `Comment` (curated from GenBank/literature, least rigorous). In the raw `genome_amr` API records the two values actually observed were `Laboratory Method` and `Computational Method` — filter strictly on `evidence == 'Laboratory Method'` (equivalently exclude any row whose `evidence` contains 'Computational' or whose `laboratory_typing_method` is empty) to get genuine wet-lab AST and discard model-generated "general phenotype" predictions, exactly as the challenge brief warns.

- `resistant_phenotype` is the SIR field itself, with observed values: `Resistant`, `Susceptible`, `Intermediate`, `Nonsusceptible`, `Susceptible-dose dependent` (rare/legacy 'Sensitive' or 'I' abbreviations may appear in older records/CLI output — normalize on ingest).

- **Scale, K. pneumoniae (NCBI `taxon_id=573`) laboratory-only AMR rows:** querying `https://www.bv-brc.org/api/genome_amr/` with `eq(taxon_id,573)` AND `eq(evidence,'Laboratory Method')` returns **85,291** total antibiotic × genome AST records (this counts rows, i.e. one genome tested against multiple drugs contributes multiple rows, so it overstates unique genomes).

  SIR class balance across those rows:

  | Class | Row count |
  |---|---|
  | Resistant | 42,084 |
  | Susceptible | 24,056 |
  | Intermediate | 3,370 |
  | Nonsusceptible | 128 |

  Top antibiotics by row count:

  | Antibiotic | Row count |
  |---|---|
  | Meropenem | 6,225 |
  | Gentamicin | 4,934 |
  | Ciprofloxacin | 4,850 |
  | Ceftazidime | 4,366 |
  | Amikacin | 3,853 |
  | Trimethoprim/sulfamethoxazole | 3,788 |
  | Ampicillin | 3,413 |
  | Piperacillin/tazobactam | 3,371 |
  | Cefepime | 3,212 |
  | Cefoxitin | 3,206 |

- Independent literature figure (Scientific Reports 2025, K. pneumoniae AMR annotation benchmarking paper) reports 18,645 K. pneumoniae genome assemblies obtained from BV-BRC overall, of which 4,976 genomes had lab AST data across 76 antibiotics/15 classes, further narrowed to 3,751 genomes after dropping antibiotics with fewer than 1,800 tested samples — a good sanity-check for expected unique-genome yield after cleaning. **To-validate:** unique genome counts were not directly queryable via the Solr facet API in this session; a distinct-genome count needs `json.facet unique(genome_id)` run from a real client — the WebFetch proxy's URL encoding could not reliably pass that query string.

- BV-BRC provides precomputed AMR gene calls that de-risk feature extraction: each genome's `<genome_id>.spgene.tab` file (and the `genome_sp_gene` API collection) contains BLASTP-based specialty-gene hits mapped from CARD, NDARO (NCBI's AMR gene DB), plus BV-BRC-curated AMR proteins, alongside virulence factors (VFDB/Victors), drug targets (DrugBank/TTD), transporters (TCDB) and essential genes. The CLI tool `p3-get-genome-sp-genes` accepts a type keyword `amr` and returns fields like `patric_id`, `antibiotics`, `antibiotics_class`, `classification`, `gene`, `genome_id`, `feature_id`. This is a useful cross-check / baseline feature source alongside running AMRFinderPlus ourselves, though for the hackathon's stated design (AMRFinderPlus via Docker/WSL2 as the canonical annotation tool) it's best used as a sanity-check/ensemble signal rather than the primary feature source, since spgene calls use a different reference DB/methodology than AMRFinderPlus and could introduce label leakage if BV-BRC's own AMR panel curation used similar gene calls to help assign phenotypes for ambiguous isolates.

- CLI tools (`p3-*` scripts) are official Perl scripts, officially released for macOS and Debian/Ubuntu (no native Windows build; a WSL2 Ubuntu install is the documented workaround, consistent with the project's existing WSL2-for-AMRFinderPlus plan). Download/install from `https://github.com/BV-BRC/BV-BRC-CLI/releases`. Login for private data via `p3-login`; anonymous/public queries need no login. Key commands: `p3-all-genomes` (list/filter genome_ids), `p3-get-genome-features` (pull features/annotations per genome), `p3-get-genome-sp-genes` (specialty/AMR gene calls), `p3-genome-fasta` (fetch contig or `--protein` FASTA for one genome_id, pipeable in a loop for bulk), `p3-all-drugs` / `p3-get-drug-genomes` / `p3-get-genome-drugs` (AMR phenotype pulls), `p3-match`, `p3-echo` for scripting glue.

## Specific choices

### Use the BV-BRC RELEASE_NOTES/PATRIC_genome_AMR.txt bulk file (FTPS) as the primary AST source, cross-validated against on-demand Data API queries to genome_amr filtered on taxon_id=573

**Choice:** Bulk flat-file download over per-genome API scraping.

**Rationale:** The flat file (tab-delimited, one row per genome-antibiotic AST result, all genomes) avoids tens of thousands of individual HTTPS/Solr calls and matches how the BV-BRC docs themselves describe it ('AMR phenotype data generated by laboratory methods'); the Data API is then used only for spot-checks, schema verification, and targeted incremental pulls (e.g. filtering by evidence or antibiotic) that the flat file's static schema can't do interactively.

### AST field mapping for the ML pipeline

`genome_id` (join key to FASTA), `antibiotic` (target label group), `resistant_phenotype` (=> SIR class: R/S/I, drop Nonsusceptible/Susceptible-dose-dependent rows or bucket into a rare-class handling policy), `evidence` (must equal 'Laboratory Method'), `laboratory_typing_method` + `testing_standard`(`+_year`) retained as provenance/metadata columns (not model features) for the report's evidence trail, `measurement`/`measurement_value`/`measurement_unit` retained only as optional MIC context (not primary target, since the challenge scores SIR calls not raw MIC regression).

**Choice:** SIR classification target = `resistant_phenotype`, filtered strictly on `evidence=='Laboratory Method'`.

**Rationale:** `resistant_phenotype` is the literal SIR phenotype field BV-BRC exposes; using it directly avoids re-deriving SIR from MIC + breakpoint tables (a much larger, error-prone undertaking for a 24h hackathon), and the `evidence` field is BV-BRC's own documented discriminator between wet-lab and model-generated calls.

### Lab-vs-predicted filter

Hard filter `eq(evidence,'Laboratory Method')` (equivalently in the flat file: keep rows whose Evidence column says Laboratory Method / AMR Panel and whose Lab Typing Method is non-empty; explicitly drop rows where Evidence contains 'Computational' or Lab Typing Method == 'Computational Prediction').

**Choice:** Filter on the `evidence` (and redundantly `laboratory_typing_method`) field, not on any phenotype/measurement field.

**Rationale:** This is the exact mechanism BV-BRC uses internally to tag AdaBoost-classifier-generated phenotypes versus true broth-dilution/VITEK2/disk-diffusion lab results, confirmed by pulling live records of both kinds; relying on any other heuristic (e.g. presence of a phenotype value) would silently include synthetic labels and violate the challenge's explicit warning against using 'general phenotype'/model-generated fields as ground truth.

## Download recipe / commands

```bash
# 1. Install BV-BRC CLI (inside WSL2 Ubuntu)
wget https://github.com/BV-BRC/BV-BRC-CLI/releases/latest/download/bvbrc-cli-installer.deb   # exact asset name varies by release -- check the releases page
sudo dpkg -i bvbrc-cli-installer.deb

# 2. Get the candidate K. pneumoniae genome_id list (public, taxon_id 573)
p3-all-genomes --eq genome_name,'Klebsiella pneumoniae' --attr genome_id --attr genome_name > kp_genomes.tsv

# 3. Bulk-download lab AST phenotypes via FTPS flat file
wget --ftp-user=anonymous --ftp-password=guest --secure-protocol=auto ftps://ftp.bv-brc.org/RELEASE_NOTES/PATRIC_genome_AMR.txt -O PATRIC_genome_AMR.txt

# 4. Filter to K. pneumoniae + Laboratory Method evidence (example with awk/python on the TSV; verify actual column order/names first)
python3 -c "import pandas as pd; df=pd.read_csv('PATRIC_genome_AMR.txt', sep='\t'); df[(df.genome_id.astype(str).str.split('.').str[0].isin(open('kp_ids.txt').read().split())) & (df.evidence=='Laboratory Method')].to_csv('kp_lab_ast.csv', index=False)"

# 5. Cross-check counts / pull incremental data via the Data API (Solr)
curl "https://www.bv-brc.org/api/genome_amr/?and(eq(taxon_id,573),eq(evidence,Laboratory+Method))&facet((field,antibiotic,limit,20),(field,resistant_phenotype))&json(nl,map)&http_accept=application/solr+json"

# 6. Bulk-download contig FASTA for the surviving (lab-AST-labeled) genome_ids only
for i in $(cut -f1 kp_lab_ast_genome_ids.txt); do wget -qN "ftps://ftp.bv-brc.org/genomes/$i/$i.fna" --ftp-user=anonymous --ftp-password=guest; done

# 7. Optional: pull BV-BRC's own precomputed AMR specialty genes for sanity-check/ensemble (not primary features)
p3-all-genomes --eq genome_id,<GENOME_ID> --attr genome_id | p3-get-genome-sp-genes amr --attr patric_id,antibiotics,antibiotics_class,classification,gene,genome_id,feature_id,patric_id > kp_spgenes.tsv

# 8. Run AMRFinderPlus (Docker, per existing project decision) on each downloaded .fna to generate the actual model features
docker run --rm -v $(pwd):/data ncbi/amr amrfinder -n /data/<genome_id>.fna -O Klebsiella_pneumoniae -o /data/<genome_id>.amrfinder.tsv
```

## Recommendations

- Install the BV-BRC CLI inside the same WSL2 Ubuntu environment already planned for AMRFinderPlus (Debian/Ubuntu build from `https://github.com/BV-BRC/BV-BRC-CLI/releases`) so both tools share one Linux toolchain and one Makefile target.
- Build the pipeline in this order: (1) fetch `RELEASE_NOTES/genome_metadata` + `PATRIC_genome_AMR.txt` for K. pneumoniae (taxon_id 573) to get the candidate genome_id list and lab AST labels; (2) filter to `evidence=='Laboratory Method'` and to antibiotics with sufficient label coverage (start with the top 10 by row count: meropenem, gentamicin, ciprofloxacin, ceftazidime, amikacin, trimethoprim/sulfamethoxazole, ampicillin, piperacillin/tazobactam, cefepime, cefoxitin); (3) bulk-download only the surviving genome_ids' `.fna` contigs via the FTP `genomes/<id>/<id>.fna` path (wget/lftp loop) rather than every K. pneumoniae genome in BV-BRC; (4) run AMRFinderPlus on those FASTAs as the feature source; (5) optionally cross-check a sample against BV-BRC's own `.spgene.tab` specialty-gene calls as a leakage/consistency sanity check, not as a training feature.
- Deduplicate/verify unique genome counts before committing to per-antibiotic training set sizes — the 85,291 figure is AST rows, not unique genomes; run an actual `unique(genome_id)` Solr `json.facet` (or count distinct genome_id in the downloaded flat file) once real tooling (curl/lftp, not the sandboxed WebFetch proxy) is available, and sanity-check against the independently published ~4,976-genome / 76-antibiotic figure for K. pneumoniae.
- Record `testing_standard` and `testing_standard_year` per row in the evidence store feeding the LLM report generator, since CLSI vs EUCAST breakpoints can flip SIR calls for the same MIC — this is directly relevant to the 'confirm with standard lab testing' disclaimer the project requires in every report.
- Apply the homology-aware grouped train/test split at the genome level using `genome_id` (and ideally strain/BioSample lineage from `genome_metadata`) as the grouping key, since multiple AST rows share the same `genome_id` (one row per antibiotic) and naive row-level splitting would leak the same isolate's genome across train/test.

## Risks & to-validate

- Genuine lab AST is sparse relative to total K. pneumoniae genomes in BV-BRC (order 5-19k total genomes vs ~5-8k with usable lab AST per the literature figure), and coverage drops fast past the top ~15 antibiotics — committing to more than ~10-15 antibiotics for the MVP risks tiny/unbalanced per-drug training sets.
- The `evidence` field has been observed with at least two literal string values in raw API data ('Laboratory Method', 'Computational Method') while the BV-BRC documentation page describes a 4-way vocabulary ('Phenotype', 'AMR Panel', 'Computational Prediction', 'Comment') — these may be UI display labels vs raw field values that don't map 1:1; a small pilot pull should enumerate every distinct value of `evidence` actually present in the K. pneumoniae subset before writing the hard filter, to avoid silently dropping valid 'AMR Panel'/'Phenotype' rows that use different literal strings than assumed.
- The FTP host (`ftp.bv-brc.org`) was unreachable via plain HTTPS from this research sandbox (connection refused) — it likely truly requires FTPS on a non-443 control/data port; confirm actual reachability and the exact `PATRIC_genome_AMR.txt` filename/path with a real FTPS client (lftp/wget) from the target dev machine before finalizing the Makefile, since the filename appeared inconsistently as both `PATRIC_genome_AMR.txt` and `PATRIC_genomes_AMR.txt` / `genome_amr.txt` across different sources. **Resolved (issue #41):** this predicted risk materialized live — the server now serves the plural name — and the fetch code tolerates both rather than pinning one; no longer open.
- SIR label noise: multiple `testing_standard` versions (CLSI vs EUCAST, and multiple years) and multiple `laboratory_typing_method`/platform combinations are pooled together in `genome_amr`; mixing breakpoint standards without tracking them can quietly corrupt the classical LR baseline's calibration — keep `testing_standard` as a stratification/metadata column, not just discard it.
- BV-BRC's own specialty-gene (`.spgene.tab`) AMR calls are partly sourced from the same CARD/NDARO lineage that informs some literature-curated phenotype comments; using spgene calls as model features while also trusting BV-BRC's 'Comment'-evidence phenotypes for labels could introduce circular/leaky signal — mitigated by strictly using only 'Laboratory Method' evidence rows as labels, per the decision above.

## Sources

- https://www.bv-brc.org/docs/quick_references/ftp.html
- https://github.com/BV-BRC/BV-BRC-Docs/blob/master/docroot/quick_references/ftp.rst
- https://www.bv-brc.org/docs/quick_references/organisms_taxon/amr_phenotypes.html
- https://www.bv-brc.org/docs/quick_references/organisms_taxon/antimicrobial_resistance.html
- https://www.bv-brc.org/docs/quick_references/organisms_taxon/specialty_genes.html
- https://www.bv-brc.org/docs/cli_tutorial/cli_getting_started.html
- https://www.bv-brc.org/docs/cli_tutorial/cli_common_tasks.html
- https://www.bv-brc.org/docs/cli_tutorial/command_list/p3-all-genomes.html
- https://www.bv-brc.org/docs/cli_tutorial/command_list/p3-get-genome-features.html
- https://www.bv-brc.org/docs/cli_tutorial/command_list/p3-get-genome-sp-genes.html
- https://www.bv-brc.org/api/genome_amr/ (live queries against taxon_id=573, evidence filters)
- https://www.bv-brc.org/api/doc/
- https://github.com/BV-BRC/BV-BRC-API
- https://github.com/BV-BRC/BV-BRC-CLI/releases
- https://www.nature.com/articles/s41598-025-24333-9 (Comparative assessment of annotation tools reveals critical antimicrobial resistance knowledge gaps in Klebsiella pneumoniae, Scientific Reports 2025 — source of the 18,645 total / 4,976 lab-AST genome figures)
