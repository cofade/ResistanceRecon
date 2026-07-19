# Roadmap

## Process (EPIC 0)

- [x] Change-control & evidence rules transferred from the reference harness (issue #35): draft-PR lifecycle + manual-test sovereignty (ADR-0010), single-source versioning (ADR-0009), skill-routing table, documentation-update matrix, branch-push CI. Every EPIC below ships its end-to-end integration test (the seven shapes in `08-crosscutting-concepts/`) — no merge without it.

## MVP (24h sprint) — K. pneumoniae, 5 antibiotics

- [x] EPIC 1 — BV-BRC data pipeline (lab-AST labels + FASTAs). Labels/metadata ingestion +
  provenance manifest shipped; feature_matrix (EPIC 2) and train/test splits (EPIC 3) are
  explicitly out of scope — see carry-forward comments on #11/#13/#17/#18. The actual live
  BV-BRC bulk pull (multi-GB FASTA download) is a separate operational step, not yet run.
- [x] EPIC 2 — Genome Reader (schemas + AMRFinderPlus runner + feature builder + MockAnnotator).
  `schemas.py` (full cross-epic contract, issue #14), `reader/fasta_parser.py` (#15), `annotation/`
  Docker runner + envelope + MockAnnotator + fixtures (#16, validated against a real Docker run),
  `reader/feature_builder.py` + committed `data/reference/ReferenceGeneCatalog.txt` (ADR-0013) +
  `feature_schema.json` (#17). PR pending user manual test.
- [ ] EPIC 3 — Predictor: split + target gate + LR + calibration + conformal + registry. PR-A
  (split/gate/LR+calibration + features/ + HTTPS fetch + batch feature-matrix builder, #18/#19/#20,
  ADRs 0015–0018) and PR-B (conformal + predict + typed-compat registry + MLflow tracking + train
  orchestration + real training run, #21/#22, ADR-0014) implemented on their branches; both pending
  user manual test before merge.
- [x] EPIC 4 — Deterministic Decision Report (LLM-free MVP). `report/{inputs,evidence,builder,narrative}.py`:
  `build_report` composes verdicts from predictor primitives (gate/model/conformal), assembles KNOWN vs
  STATISTICAL evidence deterministically (ADR-0020), and emits a `GenomeReport` with the mandatory
  disclaimer; pure-Python deterministic narrative is the demo safety net. Decoupled from `predict.py`.
  Implemented on `feat/epic4-5-report-and-llm`; draft PR pending user manual test.
- [x] EPIC 5 — Evidence RAG + grounded LLM narrative + reviewer (fail-closed). `llm/` (provider-agnostic
  client + MockLLMClient + OpenAI backend, no verdict field), `kb/` (BM25 + optional embedding + RRF,
  offline-safe, ADR-0019), `report/{nl_schemas,narrator,reviewer,pipeline}.py` (deterministic pre-check
  then LLM judge, fail-closed to the template via `NarrativeEnvelope`). Same branch; draft PR pending
  user manual test. Real OpenAI path is the user's manual test (CI is mock-only).
- [x] EPIC 6 — FastAPI backend + Streamlit UI. `service.py` in-process orchestrator
  (`analyze_genome`; ADR-0022) that both surfaces call — FASTA → reader → features →
  `predict_genome` (sovereign) → adapter → `build_report` → `narrate_report`, pinned to the
  predictor by a verdict-reconciliation test. `api/` (POST /predict, GET /health, /antibiotics,
  /model-card; structured `{ok,error}` 503/422 envelopes, never a traceback); `ui/` (Streamlit,
  in-process: firewall table ALLOW/BLOCK/REVIEW, KNOWN-vs-STATISTICAL evidence badges,
  non-dismissible disclaimer). Branched off `feat/epic4-5-report-and-llm`; `main` (PR #42)
  merged in. Draft PR pending user manual test.
- [ ] EPIC 7 — Eval harness + MODEL_CARD + DATASHEET
- [ ] EPIC 8 — Finalize Documentation + ADRs + ground-truth
- [ ] EPIC 9 — Submission (deploy, dataset publish, summary, videos, zip)

## Follow-up (post-hackathon)

- Second species: *S. aureus* / MRSA (mecA/SCCmec) — the next documented milestone.
- Full nested / repeated grouped CV with variance estimates.
- Expand the antibiotic panel (amikacin, piperacillin-tazobactam, cefepime); colistin as a harder ML-vs-rules case.
- Richer AMR-mechanism KB; ResFinder/RGI cross-annotation via hAMRonization.
- Deployment-view + quality-scenario arc42 chapters.
