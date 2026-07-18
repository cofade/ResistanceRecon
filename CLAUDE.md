# Genome Firewall — Claude Code Instructions

Genome Firewall turns a reconstructed *Klebsiella pneumoniae* genome (FASTA) into a per-antibiotic verdict — **LIKELY TO WORK / LIKELY TO FAIL / NO-CALL** — with calibrated confidence and supporting evidence. Strictly **defensive** decision support; every result must be confirmed by standard lab testing.

> Full plan: [`prd.md`](prd.md). Research ground-truth: [`Documentation/research-findings/`](Documentation/research-findings/). This project is also a live case study of the six-layer Sustainable Agentic SE framework.

## Quick reference

```bash
uv sync --all-extras                              # install (dev + optional groups)
uv run pytest                                     # tests (cov >= 80)
uv run ruff check src/ tests/ && uv run ruff format src/ tests/   # lint + format
uv run mypy src/                                  # type check (strict)
uv run bandit -r src/ --severity-level high       # security scan
uv run uvicorn genome_firewall.api.main:app --reload   # API
uv run streamlit run src/genome_firewall/ui/app.py     # demo UI
```

## Documentation map

| Need | Location |
|---|---|
| Product vision / PRD | `Documentation/01-introduction-and-goals/prd.md` |
| Verbatim challenge brief | `Documentation/01-introduction-and-goals/challenge-brief.md` |
| arc42 chapters (12) | `Documentation/NN-*/README.md` (index: `Documentation/README.md`) |
| Research & design ground-truth | `Documentation/research-findings/` |
| Architecture Decision Records | `Documentation/09-architecture-decisions/` |
| Crosscutting concepts (golden rules) | `Documentation/08-crosscutting-concepts/README.md` |
| Model card / dataset datasheet | `Documentation/MODEL_CARD.md`, `Documentation/DATASHEET.md` (EPIC 7) |
| Roadmap | `Documentation/roadmap.md` |
| Decision log (paper ground-truth) | `ground-truth/decisions.jsonl` |
| Reuse inventory (local only) | `Documentation/reuse-inventory.md` (gitignored) |

## Golden rules (non-negotiable)

1. **The LLM never predicts.** The deterministic per-antibiotic logistic-regression + calibration + conformal pipeline in `predictor/` is the SOLE source of every work/fail/no-call verdict and confidence. LLM output is never a model input. `predictor/`, `features/`, and `reader/` must not import from `llm/` (enforced by a CI import-boundary test).
2. **Defensive by construction.** This system analyzes genomes; it never designs, modifies, synthesizes, or optimizes an organism. No sequence-writing capability may be added.
3. **Ground Truth First.** Never a claim without traceable evidence. Separate a KNOWN mechanism (deterministic gene/mutation hit) from a STATISTICAL association (model/SHAP signal) — the `evidence_category` field, and honest UI wording, enforce this.
4. **Every report carries the lab-confirmation disclaimer**, enforced at three points (Pydantic validator, LLM-reviewer check, non-dismissible UI banner).
5. **No raw dicts across module boundaries.** Use the Pydantic schemas in `schemas.py`; validate all external input at the boundary.
6. **AMRFinderPlus runs only via Docker/WSL2**, isolated behind `annotation/` with an `{ok, source, error}` envelope; it is never a Python import and never runs in CI (tests use `MockAnnotator` + committed fixture TSVs).

## Workflow

| Step | Action |
|---|---|
| 1 | Plan before implementing; confirm approach |
| 2 | Read the GitHub issue / acceptance criteria |
| 3 | Feature branch: `git checkout -b feat/<epic>-<slug>` |
| 4 | Implement; run quality checks incrementally |
| 5 | Pre-commit gates (pytest, ruff, mypy, bandit) all pass |
| 6 | Present a testing checklist for human approval |
| 7 | Conventional commit `feat(<scope>): ...`; PR |
| 8 | Log the decision in `ground-truth/decisions.jsonl`; `/clear` |

**Never commit before human approval. Never skip the pre-commit gates.** Coverage drops in `predictor/` or `reader/` (the trust-critical path) require an ADR.

## Quality gates (mandatory before every PR)

1. Local gates green: `pytest` (cov ≥ 80), `ruff check`, `ruff format --check`, `mypy --strict`, `bandit -r src/ --severity-level high`, and `python scripts/check_import_boundary.py`.
2. The **senior-reviewer** agent (`.claude/agents/senior-reviewer.md`) runs against the current branch and returns "mergeable as-is" or "mergeable with [minor changes]".
3. If it raises P0s: fix, re-run the agent, loop until clean.
4. Open the PR only after 1 and 2 pass. Use `/finalize-epic` for the wrap-up (commit → push → PR → roadmap update → ground-truth log).

## Progress tracking

**Current phase:** EPIC 0 — scaffolding & six-layer harness.
**Completed:** research documentation (7 findings docs), reuse inventory, arc42 (12 chapters + 8 ADRs), repo skeleton, quality gates, CI + import-boundary gate, `.claude/` harness (senior-reviewer + skills), ground-truth log seeded.
**Next up:** GitHub epics/issues + Project board, then EPIC 1 (BV-BRC data pipeline).

Update this section at the start of each work session; do not reconstruct it from git history.

## Debugging protocol

Instrument with `print()` prefixed `[DEBUG]`; remove ALL before committing. Permanent logging uses `import logging`, never `print`.

## Known AI pitfalls (append as discovered)

Format: symptom → root cause → prevention.
- **Symptom:** an LLM narrative states a verdict the model didn't produce. **Root cause:** LLM given write access to a verdict field. **Prevention:** LLM output schemas contain no verdict/confidence field; reviewer + schema tests enforce it.
- **Symptom:** inflated held-out accuracy. **Root cause:** near-identical genomes split across train/test. **Prevention:** homology-aware grouped split (MLST + Mash fallback); explicit no-leakage test.

## ADR triggers

Write an ADR in `Documentation/09-architecture-decisions/` when: adding a dependency; a new bio data source; changing calibration/conformal/split method; any change to the LLM boundary; choosing between non-trivial approaches. Format: title, date, status, context, decision, consequences.
