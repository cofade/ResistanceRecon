# 5. Building-Block View

## Level 0 — whitebox flow

```mermaid
flowchart LR
    subgraph M1["Module 01 — Genome Reader"]
        RD["reader.fasta_parser"] --> AN["annotation\n(AMRFinderPlus / Mock)"] --> FB["reader.feature_builder"]
    end
    subgraph M2["Module 02 — Predictor (LLM-free)"]
        GATE["target_gate"] --> TR["train / calibration"] --> CO["conformal"] --> PR["predict"]
    end
    subgraph M3["Module 03 — Decision Report"]
        RB["report_builder\n(deterministic)"] --> API2["api (FastAPI)"] --> UI2["ui (Streamlit)"]
        RB -.->|optional| NAR["kb (RAG) + llm (narrate/review)"]
    end
    FB --> GATE
    PR --> RB
```

## Level 1 — the package `genome_firewall`

```
reader/      Module 01 — FASTA parse (fasta_parser.py) + feature builder (feature_builder.py,
             ReferenceGeneCatalog lookup, feature_schema.json) -- the raw-annotation-to-vector step
annotation/  AMRFinderPlus Docker/WSL2 wrapper (envelope, amrfinder.py) + MockAnnotator (mock.py,
             fixtures, CI) -- the only place a subprocess/Docker call happens (golden rule #6)
features/    Module 02 feature engineering (EPIC 3): mechanisms.py (shared AMR-mechanism
             predicates), vocabulary.py (ordered feature vocabulary + engineered combination
             features -- QRDR counts, PMQR/RMTase/carbapenemase/ESBL flags), feature_matrix.py
             (GenomeFeatureVector -> fixed-order numeric rows). Trust-critical, LLM-free.
predictor/   Module 02 (the star) — dataset, subset, split, target_gate, train, calibration, conformal, predict, model_registry, experiment_tracking
report/      Module 03a — deterministic report builder (+ jinja template) + additive LLM narrative sub-pipeline
kb/          AMR-mechanism KB: hybrid BM25 + embedding + RRF retrieval (evidence RAG)
llm/         provider-agnostic client + MockLLMClient (report narration + reviewer only)
api/         Module 03b — FastAPI (POST /predict, GET /health, /antibiotics, /model-card)
ui/          Streamlit demo (firewall table, evidence drill-down, calibration, disclaimer banner)
eval/        metrics harness (marginal + per-group + unseen-lineage)
tracking/    error-tolerant MLflow wrapper
schemas.py   Pydantic contracts crossing every boundary
constants.py canonical disclaimer, supported species/antibiotics
```

Supporting: `scripts/` (BV-BRC fetch, AMRFinderPlus batch, dataset build, env validate, import-boundary check); `data/raw/`, `data/interim/`, `data/processed/`, and `models/` (git-ignored, published as release assets) -- but `data/reference/` (pinned lookup tables like `ReferenceGeneCatalog.txt`, ADR-0013) is committed, matching the fixture-data convention rather than the bulk-data one.

## Key responsibilities & boundaries

- **Only `predictor/` produces a verdict/confidence.** It imports nothing from `llm/`.
- **`annotation/` is the only place a subprocess/Docker call happens**, always returning `{ok, source, error, data}`.
- **`report/` builds a complete `GenomeReport` with zero LLM calls** (the MVP core + demo fallback); the LLM narrative is strictly additive and receives a frozen report.

Detail: [`research-findings/architecture.md`](research-findings/architecture.md).
