# Sustainable Agentic SE Scaffolding (Six-Layer Framework)

*Transcribed from the 2026-07-18 Genome Firewall design workflow (design agent D2). Applies Sebastian Wienhold's six-layer framework as a live case study.*

## The six layers

1. **Context Engineering** — a living `CLAUDE.md` telling the agent how to work here.
2. **Quality Gates** — ruff + mypy(strict) + bandit + pytest, configured in `pyproject.toml`, enforced locally and in CI.
3. **Documentation-as-Code** — arc42 docs the agent reads, updates, and navigates.
4. **CI/CD Pipeline** — parallel lint/test/security jobs catching regressions before merge.
5. **Human-Agent Workflow** — plan-first, feature branches, human approval gate, context clearing.
6. **Entropy Management** — golden principles, error documentation, ground-truth capture, ADRs.

Core principle: **Ground Truth First — never a claim without traceable evidence.**

## Components / files to create

### CLAUDE.md (Layer 1)
- **Purpose:** Project-specific quick-reference commands (uv sync / pytest / ruff / mypy / bandit / streamlit run / uvicorn), documentation map, 8-step workflow (plan → issue branch → implement → gate → human approval → commit → PR → /clear), architecture principles including the golden rule “LLM never predicts — the deterministic per-antibiotic LR + calibration + conformal gate is the sole source of LIKELY-TO-WORK/FAIL/NO-CALL; LLM output is never a model input”, a live Known-AI-Pitfalls log, and ADR triggers (new dependency, new bio data source, new calibration/conformal choice, LLM-boundary change).
- **Reuse from:** `agentic-software-engineering/templates/CLAUDE.md`. **Path:** `CLAUDE.md`

### AGENTS.md (Layer 1)
- **Purpose:** Agent-tool-agnostic mirror of CLAUDE.md for assistants reading AGENTS.md conventions. **Reuse from:** `templates/AGENTS.md`. **Path:** `AGENTS.md`

### .claude/agents/senior-reviewer.md
- **Purpose:** Subagent used as the LLM-as-reviewer role — reviews prediction reports and PRs for grounding/hallucination before a human sees them; never touches feature vectors or model weights. **Reuse from:** `templates/.claude/agents/senior-reviewer.md`. **Path:** `.claude/agents/senior-reviewer.md`

### pyproject.toml (Layer 2)
- **Purpose:** uv-managed project with ruff (E/W/F/I/B/C4/UP/ARG/SIM/RUF), mypy `--strict` on `src/`, bandit high-severity on `src/`, pytest+coverage `fail_under=80`. Core runtime deps (pydantic, biopython, pandas, scikit-learn, fastapi, uvicorn, streamlit) + optional groups: `[ml]` mapie/crepes, `[llm]` openai/anthropic, `[tracking]` mlflow, `[dev]` pytest/ruff/mypy/bandit/pre-commit. **AMRFinderPlus is NOT a Python dep** — invoked via Docker/WSL2 subprocess, isolated behind an annotation-envelope module so it never appears in the import graph CI type-checks. **Reuse from:** `templates/pyproject.toml` + `open-garden-planner/pyproject.toml`. **Path:** `pyproject.toml`

### .pre-commit-config.yaml (Layer 2)
- **Purpose:** Local mirror of CI: ruff + ruff-format, mypy, bandit high, plus hygiene (trailing-whitespace, check-yaml/toml/json, check-added-large-files with raised maxkb for genome/AMRFinderPlus fixtures, detect-private-key for accidental API keys). **Reuse from:** `templates/.pre-commit-config.yaml`. **Path:** `.pre-commit-config.yaml`

### .github/workflows/ci.yml (Layer 4)
- **Purpose:** Three parallel jobs (lint/test/security). Hackathon-specific constraint: **AMRFinderPlus/Docker/WSL2 is NEVER invoked in CI**; the test job exercises `annotation/` against committed fixture AMRFinderPlus TSVs via a `MockAnnotator`, so the full features→ml→calibration→conformal→api pipeline is CI-tested end-to-end without the heavy tool. **Reuse from:** `templates/.github/workflows/ci.yml` + `open-garden-planner/.github/workflows/ci.yml`. **Path:** `.github/workflows/ci.yml`

### .github/workflows/release.yml (Layer 4)
- **Purpose:** PR-label semantic versioning (major/minor/patch, `chore:` exclusion, GitHub Release with generated notes). Wired AFTER the first working demo exists. **Reuse from:** `templates/.github/workflows/release.yml` + `open-garden-planner`. **Path:** `.github/workflows/release.yml`

### arc42-lite doc set (Layer 3)
- **Purpose:** 6 of 12 arc42 chapters for a 24h build: introduction/goals (defensive-only mission), constraints (no organism design/modification, self-sourced BV-BRC data, single-species-first, WSL2/Docker dependency), building-block view (annotation/features/ml/rag/llm/api/ui/eval/tracking map), runtime view (FASTA → AMRFinderPlus → features → per-antibiotic LR+calibration+conformal → RAG evidence → LLM report → Streamlit), crosscutting concepts (LLM-never-predicts golden rule, calibration+conformal methodology, homology-aware split), risks-and-technical-debt, plus roadmap and glossary. Deployment-view and quality-scenario chapters dropped for time. **Paths:** `Documentation/{01-introduction-and-goals,02-constraints,05-building-block-view,06-runtime-view,08-crosscutting-concepts,11-risks-and-technical-debt,12-glossary,roadmap}.md`

### ADR set (Layer 3+6)
- **Purpose:** One traceable decision record per key decision, seeded immediately (not retrofitted), so the paper has ground truth on WHY each choice was made and by whom (human vs agent-proposed/human-approved). **Paths:** `Documentation/09-architecture-decisions/ADR-0001-self-sourced-bvbrc-data.md`, `ADR-0002-amrfinderplus-via-docker-wsl2.md`, `ADR-0003-classical-ml-per-antibiotic-logistic-regression.md`, `ADR-0004-calibration-and-conformal-prediction-for-no-call.md`, `ADR-0005-homology-aware-grouped-split.md`, `ADR-0006-llm-boundary-rag-reviewer-report-only.md`, `ADR-0007-streamlit-fastapi-demo-stack.md`, `ADR-0008-species-scope-kpneumoniae-first.md`

### MODEL_CARD.md
- **Purpose:** Bio-ML responsible-disclosure artifact: intended use (decision SUPPORT not replacement, "confirm with standard lab testing"), training-data summary (species/antibiotics/class balance), per-antibiotic performance with calibration plots + conformal coverage, known failure modes, explicit non-goals (never organism design), out-of-scope species/antibiotics by name. **Path:** `Documentation/MODEL_CARD.md`

### DATASHEET.md
- **Purpose:** Dataset datasheet for the self-sourced BV-BRC K. pneumoniae corpus: collection process, motivation, composition (counts per antibiotic/label), known biases (geographic/temporal skew, class imbalance), preprocessing/AMRFinderPlus pipeline, explicit "what we do & don't cover" boundary (S. aureus/MRSA NOT YET covered). **Path:** `Documentation/DATASHEET.md`

### ground-truth/ capture folder (Layer 6)
- **Purpose:** Entropy-management artifact that IS the paper's data-collection mechanism: an append-only structured log of every non-trivial agent decision, human approval/rejection, and ADR trigger during the build, plus a session-log template. **Paths:** `ground-truth/README.md`, `ground-truth/decisions.jsonl`, `ground-truth/session-log-template.md`

### Code components
- **schemas.py** — Pydantic contracts (`GeneHit`, `AntibioticPrediction`, `ConformalResult`, `Report`, `RetrievedEvidence`); all module boundaries pass typed objects, never raw dicts. Reuse: `agentic-ai-challenge/schemas.py`. Path: `src/genome_firewall/schemas.py`
- **annotation/** — AMRFinderPlus Docker/WSL2 subprocess wrapper returning `{ok, source, error, data}` + `MockAnnotator` reading committed fixture TSVs. Reuse: `EPOChallenge` envelope + `validation.py`. Paths: `src/genome_firewall/annotation/{amrfinder,mock_annotator}.py`, `tests/fixtures/amrfinder/kpneumoniae_sample1.tsv`
- **features/ + ml/** — the star: feature engineering, per-antibiotic regularized LR, homology-aware grouped split, calibration, conformal prediction → the LIKELY-TO-WORK/FAIL/NO-CALL gate. Reuse: `confidence.py` pattern. Paths: `src/genome_firewall/features/build_features.py`, `ml/{split,train,calibration,conformal,predict}.py`
- **rag/** — hybrid BM25+embedding+RRF over the AMR KB. Reuse: `agentic-ai-challenge/kb/`. Paths: `src/genome_firewall/rag/{loader,chunker,retriever}.py`
- **llm/** — provider-agnostic client + MockLLMClient; two surgical uses (reviewer, grounded report). Import-isolated from `ml/`/`features/`. Reuse: `agentic-ai-challenge/llm/`. Paths: `src/genome_firewall/llm/{client,factory,reviewer}.py`, `report/generate.py`
- **api/** — async FastAPI (lifespan + CORS) wiring the pipeline. Reuse: `PatentSchmiede/backend/`. Paths: `src/genome_firewall/api/{main,config,routes}.py`
- **ui/** — Streamlit demo with the mandatory disclaimer on every report view. Path: `src/genome_firewall/ui/app.py`
- **eval/** — deterministic eval harness (per-antibiotic precision/recall/calibration-error/conformal-coverage + report groundedness). Reuse: `agentic-ai-challenge/eval/runner.py`. Path: `src/genome_firewall/eval/runner.py`
- **tracking/** — error-tolerant MLflow wrapper for training runs. Reuse: `digitalsreeni-image-annotator/.../mlflow_tracker.py`. Path: `src/genome_firewall/tracking/mlflow_tracker.py`
- **tests/conftest.py** — fixture-isolation (autouse resets, stub network/Docker) so pytest never needs AMRFinderPlus/Docker/WSL2. Reuse: `open-garden-planner/tests/conftest.py`.

## Design decisions

### Package layout
**Choice:** Single `src/genome_firewall/` package, one submodule per pipeline stage: annotation, features, ml, rag, llm, report, api, ui, eval, tracking.
**Rationale:** Mirrors the reuse assets' boundaries and turns the LLM-never-predicts golden rule into a physical, checkable package boundary rather than prose.

### CI bio-tool constraint enforcement
**Choice:** AMRFinderPlus/Docker/WSL2 never installed or invoked in GitHub Actions; commit fixture AMRFinderPlus TSVs under `tests/fixtures/amrfinder/` and drive the rest of the pipeline through a `MockAnnotator` implementing the same envelope interface.
**Rationale:** GitHub-hosted runners can't reliably run WSL2/Docker-in-Docker within a 24h budget; a mock behind a stable interface keeps the full pipeline CI-tested; interface parity means swapping in the real annotator later needs no downstream changes.

### LLM boundary enforcement mechanism
**Choice:** The `llm/` package is importable only from `rag/` and `report/`; a CI check (import-linter rule or grep-based test) fails the build if `ml/`, `features/`, or `annotation/` import anything from `llm/`.
**Rationale:** Ground-Truth-First: the calibrated + conformal ML gate must stay the sole, auditable source of each prediction. A prose rule is necessary but not sufficient — it needs a mechanical backstop an agent can't silently violate under time pressure.

### Documentation depth for a 24h build
**Choice:** arc42-lite (6 of 12 chapters + roadmap + glossary); drop deployment-view and quality-scenario; ADD two bio-specific docs (`MODEL_CARD.md`, `DATASHEET.md`).
**Rationale:** Right-sizes Layer 3 while keeping the two documents that matter most for a defensive-only bio-ML tool's honesty requirement — what the model does/doesn't cover, and what data it was trained on.

### Ground-truth capture format
**Choice:** Append-only `ground-truth/decisions.jsonl` (timestamp, decision, rationale, ADR link, agent-proposed-vs-human-approved flag) + `session-log-template.md`, populated from hour 0.
**Rationale:** This is the actual data source for the paper's case study; it must be structured and parseable, and retroactive reconstruction loses the fine-grained decision trail.

### Release automation timing
**Choice:** Seed `release.yml` from hour 0 but only enable/trigger it once a working demo exists.
**Rationale:** Semantic-version release automation has no payoff before an MVP is tagged.

### Coverage floor differentiation
**Choice:** Global `fail_under=80`, with a CLAUDE.md note that coverage drops in `ml/` or `annotation/` (the trust-critical prediction path) require an ADR, while `ui/`/`report/` have no such escalation.
**Rationale:** Not all code carries equal risk; the prediction path is what the entire defensive-decision-support claim rests on.

## Build order

1. Repo skeleton: `pyproject.toml`, `CLAUDE.md`, `AGENTS.md`, `.pre-commit-config.yaml`, `.claude/agents/senior-reviewer.md` — Layer 1+2 before any feature code.
2. `.github/workflows/ci.yml` (lint+test+security) wired against an empty `src/` + `tests/conftest.py` so the pipeline is green from the first real commit.
3. `Documentation/` arc42-lite skeleton + all 8 ADRs seeded immediately, capturing decisions already made.
4. `ground-truth/README.md` + `decisions.jsonl` + `session-log-template.md`; logging starts immediately.
5. `schemas.py` — Pydantic contracts, since every downstream module depends on these types.
6. `annotation/` AMRFinderPlus wrapper + `MockAnnotator` + fixture TSVs — unblocks CI testing of everything downstream without Docker/WSL2.
7. `features/` + `ml/` pipeline: homology-aware split → per-antibiotic LR → calibration → conformal → `predict.py`. Critical path; get it rigorous before touching LLM code.
8. `eval/` run against `ml/`; results feed `MODEL_CARD.md` and `DATASHEET.md`, written against real numbers.
9. `rag/` evidence retrieval over the AMR KB.
10. `llm/` client+factory+MockLLMClient, then `reviewer.py` and `report/generate.py` — built last, import-isolated from the start.
11. `api/` FastAPI wiring annotation→features→ml→rag→report.
12. `ui/` Streamlit calling the API, disclaimer on every view.
13. `tracking/mlflow_tracker.py` into `ml/train.py` once the loop is stable.
14. `release.yml` enabled once the first end-to-end demo works.
15. Continuous: `ground-truth/decisions.jsonl` entries at every ADR trigger or notable decision.

## Risks & to-validate

- **Biological validity:** conflating AMR gene PRESENCE (AMRFinderPlus) with PHENOTYPIC resistance (the prediction) — must be explicit in `MODEL_CARD.md` + every report disclaimer, not just code comments.
- **LLM boundary leakage:** without the mechanical CI import-check, a time-pressured agent could wire `llm/` output into a feature or confidence score “just this once,” silently violating the core integrity claim.
- **Mock/real annotator drift:** because AMRFinderPlus is never run in CI, fixture TSVs + MockAnnotator parsing can silently diverge from the real tool — needs a periodic manual re-validation (documented) against a real WSL2/Docker run.
- **Homology-aware split bugs:** grouping by accession instead of clonal lineage leaks near-identical genomes across train/test, inflating performance — the single highest-value thing to get right and test explicitly.
- **Dataset representativeness:** BV-BRC geographic/temporal submission bias + per-antibiotic class imbalance threaten calibration — `DATASHEET.md` documents this honestly.
- **Windows/WSL2/Docker fragility:** the annotation tool's only real invocation path is brittle to set up mid-hackathon — needs a clear, tested setup doc.
- **Species scope creep:** starting MRSA before K. pneumoniae is solid dilutes the depth-first strategy; ADR-0008 + CLAUDE.md progress-tracking gate this.
- **Scaffolding overhead vs 24h clock:** applying the full framework verbatim would itself consume hours; the build order is deliberately front-loaded on `ml/` and back-loaded on `release.yml`/`tracking` — a live trade-off to manage.

## Sources

Design result (reuse-grounded); grounds in the reuse assets in [`../reuse-inventory.md`](../reuse-inventory.md) and the six-layer framework in `agentic-software-engineering/`.
