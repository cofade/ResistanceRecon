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
    subgraph M3["Module 03 — Decision Report + Demo surface"]
        RB["report_builder\n(deterministic)"] -.->|optional| NAR["kb (RAG) + llm (narrate/review)"]
        SVC["service.analyze_genome\n(in-process orchestrator, ADR-0022)"] --> RB
        API2["api (FastAPI)"] --> SVC
        UI2["ui (Streamlit, in-process)"] --> SVC
    end
    FB --> GATE
    PR --> SVC
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
predictor/   Module 02 (the star) — dataset, subset, split, target_gate, train, calibration, conformal, predict, errors, model_registry, experiment_tracking (LLM-free; sole verdict source)
report/      Module 03a. Deterministic core: inputs.py (DrugPredictionInput/GenomePredictionInputs —
             the decoupled builder input, not in schemas.py), evidence.py (KNOWN/STATISTICAL/NO_SIGNAL
             tagging, ADR-0020), builder.py (build_report -> GenomeReport, zero-LLM), narrative.py
             (pure-Python deterministic render — no jinja2). Additive LLM narrative (receives the
             frozen report): nl_schemas.py (NLReportSection/ReportVerdict — no verdict field),
             narrator.py, reviewer.py (deterministic pre-check + LLM judge, fail-closed), pipeline.py
             (narrate_report -> NarrativeEnvelope). Narrator/reviewer live here, not a separate agents/.
kb/          AMR-mechanism KB (evidence RAG, retrieval-only): corpus.py (KBChunk + seed loader),
             seed/ (committed curated mechanism_chunks.jsonl), embedder.py (Embedder Protocol;
             HashingBagOfWordsEmbedder for CI, lazy SentenceTransformerEmbedder for prod),
             retriever.py (BM25 + optional dense, RRF fusion), evidence_rag.py, loader.py (offline
             catalog distiller). ADR-0019.
llm/         provider-agnostic client: types.py, errors.py, client.py (LLMClient Protocol +
             parse_structured_response), mock.py (MockLLMClient, CI), openai_backend.py (lazy,
             structured outputs), settings.py, factory.py. Report narration + reviewer only.
service.py   Module 03b orchestrator (ADR-0022): analyze_genome = FASTA -> reader -> features ->
             predict_genome (sovereign verdicts + compat guard) -> DrugPredictionInput adapter ->
             build_report (ADR-0020 evidence) -> narrate_report. The one in-process pipeline api/
             and ui/ both call; a safety-invariant test pins its report rows to predict_genome's
             verdicts+confidence so the two frozen paths never drift. The adapter emits only
             predictor primitives, never a verdict.
api/         Module 03b — FastAPI (POST /predict, GET /health, /antibiotics, /model-card); async
             lifespan (registry/retriever/LLM-client loaded once), CORS, structured
             {ok:false,error} envelopes (503 tool/pipeline failure, 422 malformed request, never a
             traceback; the client message carries no filesystem path)
ui/          Streamlit demo (in-process, no HTTP hop): firewall table (ALLOW/BLOCK/REVIEW),
             KNOWN-vs-STATISTICAL evidence badges, calibration note, non-dismissible disclaimer
             banner on every render; render.py holds the pure, fully-tested presentation logic
eval/        metrics harness (marginal + per-group + unseen-lineage)
tracking/    error-tolerant MLflow wrapper
schemas.py   Pydantic contracts crossing every boundary
constants.py canonical disclaimer, supported species/antibiotics
```

Supporting: `scripts/` (BV-BRC fetch, AMRFinderPlus batch, dataset build, env validate, import-boundary check); `data/raw/`, `data/interim/`, `data/processed/` (git-ignored, reproducible via `scripts/`), and `models/` (text artifacts + the five ~3KB per-drug `calibrated_model.joblib` are committed so the EPIC 6 demo/CI run from a bare clone, ADR-0022; large future models would be release assets) -- but `data/reference/` (pinned lookup tables like `ReferenceGeneCatalog.txt`, ADR-0013) is committed, matching the fixture-data convention rather than the bulk-data one.

## Key responsibilities & boundaries

- **Only `predictor/` produces a verdict/confidence.** It imports nothing from `llm/`.
- **`annotation/` is the only place a subprocess/Docker call happens**, always returning `{ok, source, error, data}`.
- **`report/` builds a complete `GenomeReport` with zero LLM calls** (the MVP core + demo fallback); the LLM narrative is strictly additive and receives a frozen report.

Detail: [`research-findings/architecture.md`](research-findings/architecture.md).
