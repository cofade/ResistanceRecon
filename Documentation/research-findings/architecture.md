# Repo & Module Architecture — `genome_firewall`

*Transcribed from the 2026-07-18 Genome Firewall design workflow (design agent D1). Reuse-grounded design.*

## Components

### genome_firewall.schemas

**Purpose:** Single source of truth Pydantic models for every value crossing a component boundary: GenomeInput, ContigRecord, AmrFeature, GenomeFeatureVector, GateResult, ModelPrediction, ConformalSet, EvidenceItem, AntibioticPrediction (verdict: likely_to_work|likely_to_fail|no_call, calibrated_confidence, evidence_category: known_mechanism|statistical_association|no_signal, supporting_features, target_present), GenomeReport, and the mutable GenomeFirewallState pipeline object. All models use extra='forbid', closed Literal enums, and cross-field validators (e.g. verdict<->conformal_set consistency, evidence_category<->supporting_features non-empty). No raw dicts cross any module boundary.

**Reuse from:** C:/Users/wienh/VSCode/agentic-ai-challenge/src/wscad_triage/schemas.py

**Paths to create:**
- src/genome_firewall/schemas.py

### genome_firewall.config

**Purpose:** Pydantic-settings config: data/model paths, AMRFinderPlus Docker/WSL2 invocation settings, BV-BRC endpoints, LLM provider config, calibration/conformal thresholds, feature-schema-version pin.

**Reuse from:** C:/Users/wienh/VSCode/agentic-ai-challenge/src/wscad_triage/config.py and settings.py

**Paths to create:**
- src/genome_firewall/config.py

### genome_firewall.reader (Module 01: Genome Reader)

**Purpose:** FASTA parsing/validation -> GenomeInput; AMRFinderPlus invocation via Docker/WSL2 wrapped in an ok/source/error envelope; AMR gene/point-mutation calls -> AmrFeature list -> versioned GenomeFeatureVector; optional BV-BRC spgene cross-check used only as a sanity signal, never a training feature (to avoid label leakage).

**Reuse from:** new (subprocess/Docker plumbing pattern adapted from EPOChallenge/src/epo_connectors result-envelope style)

**Paths to create:**
- src/genome_firewall/reader/__init__.py
- src/genome_firewall/reader/fasta_parser.py
- src/genome_firewall/reader/amrfinder_runner.py
- src/genome_firewall/reader/feature_builder.py
- src/genome_firewall/reader/spgene_crosscheck.py

### genome_firewall.predictor (Module 02: Predictor)

**Purpose:** BV-BRC label ingestion (filter evidence=='Laboratory Method', normalize SIR), homology-aware grouped train/test split on genome_id/lineage, deterministic molecular-target gate (rule table sourced from AMRFinderPlus resistance-hierarchy metadata), per-antibiotic regularized logistic-regression training + Platt/isotonic calibration, split-conformal prediction set computation, and the inference-time composer (predict.py) that combines gate -> model -> conformal into the final AntibioticPrediction list. This is the ONLY module allowed to produce a verdict/confidence; it has zero import of the llm/ package (enforced by a CI import-boundary test).

**Reuse from:** new (sklearn-based); confidence-composition PATTERN (not math) adapted from C:/Users/wienh/VSCode/agentic-ai-challenge/src/wscad_triage/confidence.py

**Paths to create:**
- src/genome_firewall/predictor/__init__.py
- src/genome_firewall/predictor/dataset.py
- src/genome_firewall/predictor/split.py
- src/genome_firewall/predictor/target_gate.py
- src/genome_firewall/predictor/train.py
- src/genome_firewall/predictor/calibration.py
- src/genome_firewall/predictor/conformal.py
- src/genome_firewall/predictor/predict.py
- src/genome_firewall/predictor/model_registry.py
- src/genome_firewall/predictor/experiment_tracking.py

### genome_firewall.report (Module 03a: Decision Report assembly + surgical LLM narrative)

**Purpose:** Deterministic evidence assembly (LR coefficients + gate rule citations -> EvidenceItem list) and GenomeReport building with the hardcoded mandatory 'confirm with standard lab testing' disclaimer. A separate, strictly additive LangGraph sub-pipeline (retrieve AMR-mechanism KB chunks -> draft grounded narrative -> verify groundedness -> finalize-or-fallback-to-template) generates the optional NL summary. The narrative pipeline receives only a frozen, already-finalized GenomeReport as read-only input and can never alter verdict/confidence/evidence_category.

**Reuse from:** Deterministic-routing PATTERN from C:/Users/wienh/VSCode/agentic-ai-challenge/src/wscad_triage/agents/supervisor.py + pipeline.py; worker pattern from agents/{retrieve.py,reason.py,verify.py}; RAG from kb/{loader.py,chunker.py,retriever.py}

**Paths to create:**
- src/genome_firewall/report/__init__.py
- src/genome_firewall/report/evidence.py
- src/genome_firewall/report/report_builder.py
- src/genome_firewall/report/narrative_supervisor.py
- src/genome_firewall/report/narrative_pipeline.py
- src/genome_firewall/report/agents/__init__.py
- src/genome_firewall/report/agents/retrieve.py
- src/genome_firewall/report/agents/narrate.py
- src/genome_firewall/report/agents/verify_grounding.py

### genome_firewall.llm

**Purpose:** Provider-agnostic LLM client abstraction with MockLLMClient for deterministic tests; used ONLY by report.narrative_pipeline, never by predictor/.

**Reuse from:** C:/Users/wienh/VSCode/agentic-ai-challenge/src/wscad_triage/llm/{client.py,factory.py,types.py,errors.py,anthropic_backend.py,ollama_backend.py}

**Paths to create:**
- src/genome_firewall/llm/__init__.py
- src/genome_firewall/llm/client.py
- src/genome_firewall/llm/factory.py
- src/genome_firewall/llm/types.py
- src/genome_firewall/llm/errors.py

### genome_firewall.kb

**Purpose:** Hybrid BM25+embedding retrieval (RRF) over an AMR mechanism-note corpus (CARD gene descriptions, NDARO notes, literature snippets) used solely to ground the narrative report's evidence context.

**Reuse from:** C:/Users/wienh/VSCode/agentic-ai-challenge/src/wscad_triage/kb/{loader.py,chunker.py,retriever.py}

**Paths to create:**
- src/genome_firewall/kb/__init__.py
- src/genome_firewall/kb/loader.py
- src/genome_firewall/kb/chunker.py
- src/genome_firewall/kb/retriever.py

### genome_firewall.api (Module 03b: FastAPI backend)

**Purpose:** Async FastAPI app with lifespan+CORS. Endpoints: POST /predict {fasta} -> GenomeReport (drives reader->predictor->report pipeline); GET /health (liveness + AMRFinderPlus/WSL2 reachability + model-registry-loaded envelope check); GET /antibiotics (supported drugs + per-drug model metadata); GET /model-card?antibiotic=... (training provenance, split strategy, calibration/conformal metrics, disclaimer). Tool-call failures (Docker unreachable, model missing) surface as HTTP 503 with a structured {ok:false, error} body, never a raw traceback.

**Reuse from:** C:/Users/wienh/VSCode/PatentSchmiede/backend/main.py (lifespan+CORS+/health pattern); envelope pattern from C:/Users/wienh/VSCode/EPOChallenge/src/epo_connectors/

**Paths to create:**
- src/genome_firewall/api/__init__.py
- src/genome_firewall/api/main.py
- src/genome_firewall/api/deps.py
- src/genome_firewall/api/routes/__init__.py
- src/genome_firewall/api/routes/predict.py
- src/genome_firewall/api/routes/health.py
- src/genome_firewall/api/routes/meta.py

### genome_firewall.ui (Streamlit front)

**Purpose:** Upload page (FASTA upload/paste, species selector, calls POST /predict); Firewall rule table (sortable verdict/confidence/evidence-category table); Evidence drill-down (per-antibiotic supporting_features, raw AMRFinderPlus hit details, LLM narrative paragraph clearly labeled as AI-generated); Calibration/reliability page (reliability diagrams, conformal coverage, class balance, split strategy description). A persistent banner component renders the mandatory lab-confirmation disclaimer on every page, hardcoded client-side so it survives backend outages.

**Reuse from:** new

**Paths to create:**
- src/genome_firewall/ui/streamlit_app.py
- src/genome_firewall/ui/pages/1_upload.py
- src/genome_firewall/ui/pages/2_firewall_table.py
- src/genome_firewall/ui/pages/3_evidence_drilldown.py
- src/genome_firewall/ui/pages/4_calibration.py
- src/genome_firewall/ui/components/banner.py

### data acquisition & environment scripts

**Purpose:** BV-BRC FTPS+Data API bulk ingestion (genome_metadata, PATRIC_genome_AMR.txt, per-genome FASTA for label-bearing genomes only); WSL2 Docker AMRFinderPlus batch runner; end-to-end raw->processed dataset builder; per-antibiotic training loop; environment validation smoke-test (PASS/FAIL/SKIP/WARN) covering WSL2/Docker reachability, AMRFinderPlus DB version, model artifacts loadable, BV-BRC reachability.

**Reuse from:** C:/Users/wienh/VSCode/EPOChallenge/src/epo_connectors/validation.py (PASS/FAIL/SKIP/WARN smoke-test pattern + ok/error envelope)

**Paths to create:**
- scripts/fetch_bvbrc_data.py
- scripts/run_amrfinder_batch.sh
- scripts/build_dataset.py
- scripts/train_all.py
- scripts/validate_environment.py
- scripts/predict_cli.py

### data & model artifact layout

**Purpose:** data/raw/bvbrc/{genome_metadata.tsv,PATRIC_genome_AMR.txt,fasta/<genome_id>.fna}; data/interim/amrfinder_calls/<genome_id>.tsv; data/processed/{feature_matrix.parquet,labels.parquet,splits/train_test_genome_ids.json}; models/<antibiotic_slug>/v<N>/{model.joblib,calibrator.joblib,conformal.json,feature_schema.json,metrics.json,model_card.md} -- versioned so predict.py can validate a genome's feature vector against the exact training-time schema and AMRFinderPlus DB version, raising a typed error rather than silently misaligning.

**Reuse from:** new

**Paths to create:**
- data/raw/bvbrc/
- data/interim/amrfinder_calls/
- data/processed/
- models/

### tests & CI/quality gates

**Purpose:** Unit tests per module, integration test for the full predict pipeline against fixture FASTA + fixture AMRFinderPlus output, eval harness computing per-antibiotic sensitivity/specificity/AUC/ECE/conformal coverage, fixture-isolation conftest, plus a dedicated CI check asserting predictor/ has zero import of llm/. 3-job CI (lint+test+security) with PR-label semantic-versioned releases.

**Reuse from:** C:/Users/wienh/VSCode/open-garden-planner/tests/conftest.py (fixture isolation); C:/Users/wienh/VSCode/agentic-ai-challenge/src/wscad_triage/eval/runner.py (eval harness pattern); C:/Users/wienh/VSCode/agentic-software-engineering/templates/.github/workflows/{ci.yml,release.yml} and open-garden-planner/.github/workflows/{ci.yml,release.yml}

**Paths to create:**
- tests/conftest.py
- tests/unit/
- tests/integration/
- tests/eval/runner.py
- tests/fixtures/sample_genome.fna
- tests/fixtures/sample_amrfinder_output.tsv
- .github/workflows/ci.yml
- .github/workflows/release.yml

### project governance docs

**Purpose:** CLAUDE.md/AGENTS.md context files (defensive-use-only principle stated up front), arc42 architecture docs, ADRs (esp. one documenting the deterministic-gate-before-model boundary and one documenting the LangGraph-only-in-narrative-layer decision).

**Reuse from:** C:/Users/wienh/VSCode/agentic-software-engineering/templates/ (CLAUDE.md, AGENTS.md, pyproject.toml, .pre-commit-config.yaml)

**Paths to create:**
- CLAUDE.md
- AGENTS.md
- pyproject.toml
- .pre-commit-config.yaml
- docs/arc42/
- docs/adr/

## Design decisions

### Scope of the LangGraph/agent-graph pattern

**Choice:** Reserve LangGraph strictly for the report/narrative sub-pipeline (RAG retrieve -> draft -> verify-groundedness -> finalize-or-template-fallback). The core prediction path (parse -> annotate -> feature-build -> deterministic gate -> per-drug model -> conformal -> verdict) is a plain deterministic Python function chain, not a graph.

**Rationale:** Every branch in the core prediction path is a pure function of data (gate fires or not, conformal set size); there is no LLM-judgment branch to route around. LangGraph's value only appears where an LLM's output groundedness must gate inclusion, i.e. the narrative layer -- keeping it out of predictor/ also makes the 'LLM never in the prediction path' constraint mechanically checkable via an import-boundary test.

### Deterministic molecular-target gate precedes the learned model, per antibiotic

**Choice:** A rule table sourced from AMRFinderPlus's own resistance-hierarchy metadata (element Type=AMR, Subtype gene/POINT, Hierarchy node -> drug/drug-class mapping) short-circuits the LR+conformal step for antibiotics where a known resistance mechanism is called (e.g. any carbapenemase gene => likely_to_fail for carbapenems), tagging evidence_category=known_mechanism with a fixed high confidence.

**Rationale:** Reflects real clinical microbiology practice where known-mechanism resistance is not a statistical question, gives a transparent floor of trust independent of calibration quality, and directly serves the Ground-Truth-First principle ('never a claim without traceable evidence'). Sourcing the rule table from AMRFinderPlus's own metadata (rather than a hand-maintained list) keeps the gate and the annotation tool in lockstep as the reference DB updates.

### Feature schema versioning with explicit inference-time compatibility check

**Choice:** Every trained model artifact ships feature_schema.json (ordered gene/mutation feature names + pinned AMRFinderPlus DB version hash); predictor/predict.py raises a typed error rather than silently reindexing/padding when a new genome's feature vector doesn't match.

**Rationale:** Prevents the classic silent-misalignment failure mode where a reference-DB update shifts gene naming/columns and predictions quietly become garbage with no visible error -- enforces the 'no raw dicts, explicit validation' principle at the model I/O boundary specifically.

### Uniform ok/source/error envelope for every external tool and network call

**Choice:** Wrap every AMRFinderPlus Docker/WSL2 invocation and every BV-BRC fetch in an {ok, source, error} envelope; the FastAPI layer translates envelope failures into HTTP 503 with a structured error body, never a raw exception traceback reaching the Streamlit UI.

**Rationale:** The most likely live-demo failure mode is the WSL2/Docker AMRFinderPlus dependency being unreachable; graceful, legible degradation beats a stack trace during a hackathon demo, and the pattern is already proven in the EPOChallenge reuse asset.

### Split-conformal prediction on top of calibrated per-drug logistic regression

**Choice:** Compute nonconformity scores from the calibration fold's calibrated LR probabilities per antibiotic (Mondrian/class-conditional if imbalance requires it); a prediction set containing both classes maps to no_call.

**Rationale:** Gives a coverage-guaranteed, principled no-call mechanism instead of an arbitrary confidence threshold, matching the project's explicit prior decision to use calibration + conformal prediction for no-call.

### Homology-aware grouped train/test split keyed on genome_id (+ lineage where available)

**Choice:** Use group-based splitting (sklearn GroupShuffleSplit/GroupKFold) on genome_id joined against BV-BRC genome_metadata lineage/BioSample, never a plain random row split.

**Rationale:** AST rows share genome_id (one row per antibiotic per isolate); naive row-level splitting leaks the same isolate's genome across train/test and inflates apparent accuracy -- already identified as a concrete risk in the BV-BRC research findings.

### narrative_pipeline receives a frozen, already-finalized GenomeReport as read-only input

**Choice:** The LLM narrative step is structurally forbidden from writing back into verdict/calibrated_confidence/evidence_category/supporting_features -- it only consumes an immutable copy and appends narrative_summary.

**Rationale:** Makes 'LLMs never in the prediction path' a type-level guarantee rather than a convention, closing the most likely way an LLM could silently influence a safety-relevant verdict.

## Build order

1. src/genome_firewall/schemas.py -- all Pydantic models (GenomeInput, AmrFeature, GenomeFeatureVector, GateResult, ModelPrediction, ConformalSet, EvidenceItem, AntibioticPrediction, GenomeReport, GenomeFirewallState); everything downstream imports these.
2. src/genome_firewall/config.py -- settings for data/model paths, AMRFinderPlus Docker/WSL2 invocation, BV-BRC endpoints, thresholds.
3. src/genome_firewall/reader/fasta_parser.py + tests/fixtures/sample_genome.fna -- FASTA ingestion/validation, no external dependency yet.
4. scripts/fetch_bvbrc_data.py -- BV-BRC FTPS + Data API pull (genome_metadata, PATRIC_genome_AMR.txt, per-genome FASTA for label-bearing genome_ids only); produces the real training data that steps 7+ depend on.
5. src/genome_firewall/reader/amrfinder_runner.py -- Docker/WSL2 AMRFinderPlus wrapper with ok/error envelope; validate against a handful of downloaded genomes from step 4.
6. src/genome_firewall/reader/feature_builder.py -- AMR gene/mutation calls -> AmrFeature list -> GenomeFeatureVector, emitting feature_schema.json. Module 01 is now end-to-end testable.
7. src/genome_firewall/predictor/dataset.py + split.py -- BV-BRC label ingestion (evidence=='Laboratory Method' filter, SIR normalization), homology-aware grouped train/test split.
8. src/genome_firewall/predictor/target_gate.py -- deterministic rule table sourced from AMRFinderPlus hierarchy metadata.
9. src/genome_firewall/predictor/train.py + calibration.py -- per-antibiotic regularized LR + Platt/isotonic calibration for the top-10 antibiotics by label coverage.
10. src/genome_firewall/predictor/conformal.py -- split-conformal wrapper on calibrated probabilities -> prediction sets.
11. src/genome_firewall/predictor/predict.py + model_registry.py -- inference-time composition of gate+model+conformal into AntibioticPrediction list; Module 01+02 fully testable end-to-end here.
12. src/genome_firewall/report/evidence.py + report_builder.py -- assemble GenomeReport from predictions with the hardcoded disclaimer, no LLM yet -- this is the first working LLM-free MVP.
13. src/genome_firewall/api/main.py + routes/{predict,health,meta}.py -- FastAPI surface wrapping the deterministic pipeline; first curl-able demoable slice.
14. src/genome_firewall/llm/ + kb/ -- copy/adapt provider abstraction and hybrid retrieval; load AMR mechanism-note corpus (CARD descriptions, gene function text) as the KB.
15. src/genome_firewall/report/agents/{retrieve,narrate,verify_grounding}.py + narrative_supervisor.py + narrative_pipeline.py -- the LangGraph narrative sub-pipeline, strictly additive to the report.
16. src/genome_firewall/ui/streamlit_app.py + pages -- Streamlit front consuming the FastAPI backend, in order: Upload -> Firewall table -> Evidence drill-down -> Calibration page.
17. .github/workflows/{ci.yml,release.yml}, CLAUDE.md, AGENTS.md, docs/arc42/, docs/adr/ -- CI/CD and documentation-as-code wiring (scaffold early in parallel with steps 1-3 per the six-layer framework, but finalize once tests from steps 6-13 exist to gate on).
18. scripts/validate_environment.py -- end-to-end PASS/FAIL/SKIP/WARN smoke test (WSL2/Docker reachability, AMRFinderPlus DB version, model artifacts loadable, BV-BRC reachability) as final pre-demo polish.

## Risks & to-validate

- AMRFinderPlus Docker/WSL2 dependency is a single point of failure for a live demo; mitigate with a pre-computed feature-vector cache for a small set of demo genomes plus the ok/error envelope so a live failure degrades to a clear error banner rather than a crash.
- Per-antibiotic label counts vary hugely (top-10 antibiotics range roughly 3,200-6,200 AST rows before the homology-aware grouped split shrinks the effective unique-genome count further); some antibiotics may never reach a reliably calibrated model -- handle by hard-coding an 'insufficient training data' no_call rather than emitting an unstable prediction, decided per-antibiotic at train.py time and recorded in that drug's model_card.md.
- The deterministic gate table, even when sourced from AMRFinderPlus's own hierarchy metadata, can silently under-fire if a resistance mechanism is present but not yet cataloged in that AMRFinderPlus DB release, letting the statistical model override a genuinely known mechanism -- mitigate by pinning and recording the AMRFinderPlus DB version in every model_card and treating DB upgrades as a versioned, re-validated event, not a silent swap.
- Risk of LLM narrative leaking into the safety-relevant verdict/confidence if module boundaries are not enforced -- mitigate with a CI test that statically asserts predictor/ imports nothing from llm/, and by typing narrative_pipeline's input as an already-validated, effectively-frozen GenomeReport.
- Feature schema drift between the AMRFinderPlus database version used at training time and at inference time is the classic silent-failure vector for this kind of pipeline -- mitigated by the feature_schema.json + typed-error compatibility check (see decisions), but requires actual discipline in scripts/train_all.py and the Docker image tag to pin versions consistently.
- BV-BRC's evidence field vocabulary was observed with only two literal values ('Laboratory Method','Computational Method') against documentation describing four -- if additional literal strings appear in the full pull (e.g. 'AMR Panel', 'Phenotype'), the current hard filter in predictor/dataset.py could silently under-collect valid lab-derived labels; scripts/fetch_bvbrc_data.py should enumerate and log all distinct evidence values seen before dataset.py's filter is finalized.
