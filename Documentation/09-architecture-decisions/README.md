# Architecture Decision Records

One record per non-trivial, hard-to-reverse decision. Format: Title, Date, Status, Context, Decision, Consequences. New ADR triggers: adding a dependency, a new bio data source, changing calibration/conformal/split method, any LLM-boundary change, choosing between non-trivial approaches.

| ADR | Decision | Status |
|---|---|---|
| [0001](ADR-0001-self-sourced-bvbrc-data.md) | Self-source lab-AST data from BV-BRC | Accepted |
| [0002](ADR-0002-amrfinderplus-via-docker-wsl2.md) | AMRFinderPlus via pinned Docker/WSL2 | Accepted |
| [0003](ADR-0003-classical-ml-per-antibiotic-logistic-regression.md) | Per-antibiotic L2 logistic regression | Accepted |
| [0004](ADR-0004-calibration-and-conformal-prediction-for-no-call.md) | Sigmoid calibration + conformal no-call | Accepted |
| [0005](ADR-0005-homology-aware-grouped-split.md) | Homology-aware grouped split | Accepted |
| [0006](ADR-0006-llm-boundary-rag-reviewer-report-only.md) | LLM boundary: RAG/reviewer/report only | Accepted |
| [0007](ADR-0007-streamlit-fastapi-demo-stack.md) | Streamlit + FastAPI demo stack | Accepted |
| [0008](ADR-0008-species-scope-kpneumoniae-first.md) | K. pneumoniae first, MRSA follow-up | Accepted |
