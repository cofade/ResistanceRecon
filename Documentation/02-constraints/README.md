# 2. Architecture Constraints

## Technical

| Constraint | Consequence |
|---|---|
| **Defensive-only** | No organism design/modification/synthesis capability may exist in the codebase. Input FASTA is read-only. |
| **Self-sourced data** | No organizer dataset; data comes from BV-BRC, lab-measured AST only (`evidence == 'Laboratory Method'`). See [ADR-0001](09-architecture-decisions/ADR-0001-self-sourced-bvbrc-data.md). |
| **AMRFinderPlus is Linux/Docker-native** | Runs only via pinned Docker under WSL2, isolated behind `annotation/`; never a Python import; never in CI. See [ADR-0002](09-architecture-decisions/ADR-0002-amrfinderplus-via-docker-wsl2.md). |
| **Single species first** | K. pneumoniae only at MVP; MRSA is a documented follow-up. See [ADR-0008](09-architecture-decisions/ADR-0008-species-scope-kpneumoniae-first.md). |
| **LLM never predicts** | Verdicts/confidence come only from the deterministic pipeline; `predictor/`/`features/`/`reader/` may not import `llm/` (CI-enforced). See [ADR-0006](09-architecture-decisions/ADR-0006-llm-boundary-rag-reviewer-report-only.md). |
| **24-hour build** | Depth over breadth; arc42-lite (6 chapters); quality never sacrificed for speed. |

## Organizational / process

- Team: Sebastian Wienhold + Claude (Fable 5). Six-layer Sustainable Agentic SE framework applied as a live case study; every decision logged in `ground-truth/decisions.jsonl`.
- Deliverables tie to the Hack-Nation checklist (project summary, demo/tech/team videos, public repo, zipped code, dataset link).

## Conventions

- Python 3.11+, `uv`, `src/` layout, Pydantic-everywhere (no raw dicts across boundaries).
- Quality gates: ruff, mypy `--strict`, bandit high, pytest coverage ≥ 80.
- Apache-2.0 license; conventional commits; feature branch per issue; human approval gate.
