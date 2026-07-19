# Datasheet — Genome Firewall training/evaluation dataset

> Follows the *Datasheets for Datasets* framing (Gebru et al., 2021). Every figure is drawn from
> a committed artifact — the label-ingestion manifest (`data/processed/dataset_manifest.json`,
> reproducible via `scripts/build_dataset.py`) and the model registry — not from memory.
> The processed data itself is gitignored (large; reproducible via the scripts / release assets);
> its provenance and shape are recorded here.

## Motivation

To turn a reconstructed *Klebsiella pneumoniae* genome into a calibrated, per-antibiotic
work/fail/no-call verdict as **defensive** decision support (confirm every result by lab AST).
The dataset is self-sourced from BV-BRC lab-measured antimicrobial susceptibility, chosen over
model-generated labels so the ground truth is genuine wet-lab measurement (ADR-0001).

## Composition

### Source labels (full BV-BRC *K. pneumoniae* lab-AST pull)

| Stage | Count |
|---|---|
| Raw `PATRIC_genome_AMR` rows (taxon 573, evidence = *Laboratory Method*) | 85,291 |
| Lab rows kept (non-empty typing method) | 80,645 |
| Labels after duplicate resolution (majority vote per genome × drug) | 64,237 |
| Dropped — contradictory duplicates | 116 |
| Dropped — uncanonical/blank SIR | 15,650 |
| **Unique genomes with a usable label** | **5,227** |

Raw phenotype distribution (pre-collapse): Resistant 42,084 · Susceptible 24,056 · Intermediate
3,370 · Nonsusceptible 128 · blank 15,653. The binary collapse (ADR-0017) keeps only unambiguous
Resistant→R / Susceptible→S; Intermediate, Nonsusceptible, and Susceptible-dose-dependent are
dropped as ambiguous label-noise rather than force-mapped.

Panel drugs in the source (R / S / Intermediate, unique genomes, breakpoint standard split):

| Antibiotic | R | S | I | genomes | CLSI / EUCAST / other |
|---|---|---|---|---|---|
| ciprofloxacin | 2,406 | 688 | 82 | 4,157 | 2,488 / 914 / 781 |
| trimethoprim-sulfamethoxazole | 2,104 | 720 | 15 | 3,097 | 2,487 / 458 / 178 |
| ceftriaxone | 2,145 | 417 | 62 | 2,902 | 2,468 / 194 / 251 |
| gentamicin | 1,516 | 2,049 | 111 | 4,239 | 2,523 / 1,056 / 687 |
| meropenem | 1,463 | 1,904 | 157 | 5,433 | 4,060 / 853 / 624 |

### Modelled subset (what the committed models were trained + evaluated on)

A **130-genome, 67-homology-group (64 STs + 3 singletons)** subset with FASTA downloaded and
AMRFinderPlus-annotated (186 features, DB `2026-05-15.1`). This is a thin MVP demonstration cut,
not the full 5,227-genome label set. Per-drug modelled label counts, split sizes, and metrics are
in `models/results_summary.json`, each `models/<drug>/v1/metrics.json`, and `models/eval_summary.json`.

## Collection process

- **Labels:** BV-BRC FTPS (`ftp.bv-brc.org`) `PATRIC_genome_AMR` flat file + `genome_metadata`,
  pure-Python fetch (ADR-0012; the HTTPS Data API is the primary path per ADR-0016, with the
  flat-file name tolerant of the `PATRIC_genome_AMR.txt`↔`PATRIC_genomes_AMR.txt` drift, issue #41).
- **Filtering:** `evidence == "Laboratory Method"` only, non-empty `laboratory_typing_method`
  required; SIR canonicalised; duplicates resolved by majority vote with clinical-opposite
  contradictions dropped.
- **Genomes:** contig FASTA via the BV-BRC HTTPS Data API with a contig-count/length sanity check
  against the genome record (ADR-0016).
- **Features:** AMRFinderPlus via pinned Docker/WSL2 (ADR-0002), against the committed
  `data/reference/ReferenceGeneCatalog.txt` (ADR-0013). AMRFinderPlus never runs in CI.
- **Homology grouping:** MLST sequence type from `genome.mlst` (ADR-0005); genomes without a
  usable ST fall back to a leakage-safe per-genome singleton (ADR-0015). In the source metadata,
  36,885 / 39,628 genomes carried a usable ST (6.9% missing).

## Uses

Intended: train and evaluate the deterministic defensive predictor; publish honest evaluation
(this datasheet + `MODEL_CARD.md`). **Out of scope / must not:** any use that designs, modifies,
synthesises, or optimises an organism, or that treats a verdict as a substitute for laboratory AST.

## Distribution & maintenance

Source data is public (BV-BRC). Processed artifacts (`data/raw|interim|processed/`, `*.joblib`)
are gitignored and reproducible via `scripts/fetch_bvbrc_data.py` → `build_dataset.py` →
`build_feature_matrix.py`; the small text artifacts under `models/` (metrics/schema/conformal/
coefficients JSON, cards, `results_summary.json`, `eval_summary.json`) are committed as
ground-truth. Tool versions at build: Python 3.12, pandas 2.3.

## Limitations & biases

- **Breakpoint mixing:** phenotypes span CLSI and EUCAST standards (and blanks), which can flip an
  S/R call for the same MIC — a real label-noise source, surfaced per drug above.
- **Sampling bias:** BV-BRC over-represents sequenced epidemic/resistant clones (e.g. ST258/ST307),
  so neither class balance nor lineage coverage is population-representative.
- **Thin modelled subset:** the committed models see 130 genomes, not 5,227; several per-drug
  folds are single-class. Treat downstream metrics as indicative (see `MODEL_CARD.md`).
- **MLST coverage:** ~6.9% of source genomes lack a usable ST and fall back to singletons.
- **Missing FASTA at label time:** the label manifest records `genomes_with_fasta = 0` — FASTA
  download + annotation is a separate downstream stage; the 130-genome subset is its output.
