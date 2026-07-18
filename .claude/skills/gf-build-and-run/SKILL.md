---
name: gf-build-and-run
description: How to install, test, and run Genome Firewall locally (quality gates, FastAPI backend, Streamlit demo, CLI). Read before running anything in this repo.
user_invocable: true
---

# Build & Run Genome Firewall

## Install

```bash
uv sync --all-extras
uv run pre-commit install
```

## Quality gates (all must be green before any commit)

```bash
uv run pytest                                                   # tests, coverage >= 80
uv run ruff check src/ tests/ && uv run ruff format --check src/ tests/
uv run mypy src/                                                # strict
uv run bandit -r src/ scripts/ --severity-level high
uv run python scripts/check_import_boundary.py                  # LLM boundary gate
```

## Run

```bash
uv run uvicorn genome_firewall.api.main:app --reload           # FastAPI backend
uv run streamlit run src/genome_firewall/ui/app.py             # demo UI
uv run genome-firewall --help                                  # CLI (once implemented)
```

## Notes

- **Tests never need Docker or AMRFinderPlus** — they use `MockAnnotator` + committed fixture TSVs (`tests/fixtures/amrfinder/`).
- The **deterministic path works with no OpenAI key**. Set `OPENAI_API_KEY` only to enable the optional grounded narrative + LLM reviewer.
- Building the feature matrix / training models needs AMRFinderPlus via Docker/WSL2 — see the `gf-data-and-annotation` skill. That is offline/dev only.
