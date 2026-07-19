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
- [ ] EPIC 3 — Predictor: split + target gate + LR + calibration + conformal + registry
- [ ] EPIC 4 — Deterministic Decision Report (LLM-free MVP)
- [ ] EPIC 5 — Evidence RAG + grounded LLM narrative + reviewer (fail-closed)
- [ ] EPIC 6 — FastAPI backend + Streamlit UI (firewall table + disclaimer)
- [ ] EPIC 7 — Eval harness + MODEL_CARD + DATASHEET
- [ ] EPIC 8 — Finalize Documentation + ADRs + ground-truth
- [ ] EPIC 9 — Submission (deploy, dataset publish, summary, videos, zip)

## Follow-up (post-hackathon)

- Second species: *S. aureus* / MRSA (mecA/SCCmec) — the next documented milestone.
- Full nested / repeated grouped CV with variance estimates.
- Expand the antibiotic panel (amikacin, piperacillin-tazobactam, cefepime); colistin as a harder ML-vs-rules case.
- Richer AMR-mechanism KB; ResFinder/RGI cross-annotation via hAMRonization.
- Deployment-view + quality-scenario arc42 chapters.
