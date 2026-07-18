# AGENTS.md — Genome Firewall

Agent-tool-agnostic instructions. The full, authoritative guidance lives in [`CLAUDE.md`](CLAUDE.md) — read it. This mirror exists for assistants that follow the `AGENTS.md` convention.

**One-line:** Genome Firewall predicts per-antibiotic response (work / fail / no-call) from a *K. pneumoniae* genome, with calibrated confidence and evidence. Strictly defensive decision support; confirm every result with standard lab testing.

## The rules that matter most

1. The LLM **never** predicts. Verdicts/confidence come only from the deterministic `predictor/` pipeline (LR + calibration + conformal). `predictor/`, `features/`, `reader/` never import `llm/`.
2. Defensive by construction: analyze genomes only; never design/modify/synthesize an organism.
3. Ground Truth First: separate KNOWN mechanism from STATISTICAL association; every claim traceable.
4. Every report shows the lab-confirmation disclaimer (three enforcement points).
5. No raw dicts across boundaries — use the `schemas.py` Pydantic models.
6. AMRFinderPlus runs only via Docker/WSL2 behind `annotation/`; never imported; never in CI (use `MockAnnotator` + fixtures).

## Commands & workflow

See [`CLAUDE.md`](CLAUDE.md) “Quick reference”, “Plan Mode”, and “Workflow (change lifecycle)” for the authoritative detail. In short:

- **Plan Mode first** for any non-trivial change: read the issue/acceptance criteria + roadmap + ADRs + arc42 docs, analyze existing code, propose the smallest viable design, surface at least one alternative and its failure modes, agree with the user, then implement.
- **Feature branch for every change** (code, docs, CI, refactor) — never commit directly to `main`.
- **Quality gates** (pytest cov ≥ 80, ruff, mypy strict, bandit high, import-boundary) must pass, then a **fresh-worktree senior-reviewer pass** with re-review until no P0/P1 remain.
- **Every user story ships an end-to-end integration test** — no merge without it.
- **A draft PR is the normal end state.** It stays draft, carrying a manual-testing checklist, until the user explicitly confirms manual testing passed; only then mark ready and merge. Automated green is necessary but never sufficient — **manual testing is sovereign.**
- Evidence hierarchy (weakest → sovereign): green CI < full local gates < independent senior review < manual testing.
- Log every notable decision in `ground-truth/decisions.jsonl` in the same session; update docs per the change-type matrix. Never create git tags manually (release automation is deferred; see `gf-change-control`).
