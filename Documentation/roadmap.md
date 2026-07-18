# Roadmap

## MVP (24h sprint) — K. pneumoniae, 5 antibiotics

- [ ] EPIC 1 — BV-BRC data pipeline (lab-AST labels + FASTAs)
- [ ] EPIC 2 — Genome Reader (schemas + AMRFinderPlus runner + feature builder + MockAnnotator)
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
