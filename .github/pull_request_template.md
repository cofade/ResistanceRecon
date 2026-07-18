<!-- Open as a DRAFT PR. It stays draft until the author confirms manual testing passed. See gf-change-control. -->

## Summary

- <what changed and why, in bullets>
- <linked issue / epic + acceptance criteria>

## Automated test results

- [ ] `uv run pytest` (coverage ≥ 80) — <pass/fail + notable numbers>
- [ ] `ruff check` + `ruff format --check` + `mypy --strict` + `bandit -r src/ --severity-level high` + `check_import_boundary.py` green
- [ ] End-to-end integration test for this user story present (`@pytest.mark.integration`, MockAnnotator)

## Senior-reviewer

- [ ] `senior-reviewer` run on a fresh worktree/diff vs `main`
- [ ] All P0/P1 resolved; **re-reviewed after fixes** until clean
- Re-review status: <clean / outstanding items>

## Manual-testing checklist (falsifiable — the sovereign gate)

> The PR stays **draft** until these pass and the author explicitly confirms. Each item: action → expected observable outcome.

- [ ] <action> → <expected outcome>
- [ ] OOD / novel input → NO-CALL, not a confident guess
- [ ] External-tool / OpenAI outage → structured 503 / graceful degraded path
- [ ] Every report path shows the non-dismissible lab-confirmation disclaimer

## Documentation / ADR / ground-truth

- [ ] Docs updated per the change-type matrix (`CLAUDE.md` / `gf-docs-and-writing`)
- [ ] ADR written if triggered; index README row added
- [ ] `ground-truth/decisions.jsonl` appended this session
- [ ] Roadmap / progress table updated

## Safety invariants (confirm none violated)

- [ ] The LLM path cannot influence a verdict/confidence (no verdict field on LLM schemas; `predictor/` imports no `llm/`)
- [ ] No train/test leakage across the homology-aware split
- [ ] The lab-confirmation disclaimer is present on every report path

## Known limitations & deferred work

- <what this PR intentionally does not cover; follow-up issues/TD items>

🧙 Built with [WOZCODE](https://wozcode.com)
