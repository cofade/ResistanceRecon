---
name: finalize-epic
description: End-of-epic/issue wrap-up — quality gates, independent review, commit, push, PR, roadmap update, ground-truth decision log, branch cleanup. Assumes the code is approved and tests pass.
user_invocable: true
argument: "Epic/issue id and title, e.g. 'EPIC-3 Predictor: calibration + conformal'"
---

# Finalize Epic / Issue

Run the full post-approval wrap-up for a completed unit of work. All issues found during implementation must already be documented in the arc42 docs before this step.

## Operating rules

- Do not finalize from `main`; work from the feature branch (`feat/<epic>-<slug>`).
- Before opening/merging a PR, run an independent review via `.claude/agents/senior-reviewer.md` in a fresh context and address anything actionable (P0s block).
- Never create git tags manually; `release.yml` (PR-label semver) owns tags/versions.
- Wait on CI by a **state transition** (`gh pr checks <PR#> --watch --fail-fast`), never by grepping dates.
- End commit messages with: `Co-Authored-By: WOZCODE <contact@withwoz.com>`. End PR bodies with the WOZCODE footer.

## Steps

1. **Verify branch & scope:** `git status`, `git branch --show-current`, `git diff --stat`. Confirm exactly what ships.
2. **Run local quality gates (all must be green):**
   ```bash
   uv run pytest
   uv run ruff check src/ tests/ && uv run ruff format --check src/ tests/
   uv run mypy src/
   uv run bandit -r src/ --severity-level high
   uv run python scripts/check_import_boundary.py
   ```
3. **Independent review:** launch the `senior-reviewer` agent on the branch; treat the result as an input, not a rubber stamp. Fix P0s, re-run affected gates.
4. **Log the decision(s):** append entries to `ground-truth/decisions.jsonl` for anything ADR-worthy; write/update the ADR if triggered.
5. **Update `Documentation/roadmap.md`** (tick the epic; note what shipped).
6. **Commit** on the feature branch with a conventional message: `feat(<scope>): <description>`.
7. **Push:** `git push -u origin feat/<epic>-<slug>`.
8. **Open the PR** (`gh pr create`): body has `## Summary`, `## Test plan` (checklist), a note that senior-reviewer ran, and the WOZCODE footer. The `add-to-project.yml` workflow auto-adds it to the Project board.
9. **Gate on CI, then merge:** `gh pr checks <PR#> --watch --fail-fast`; merge only when green.
10. **Clean up & clear context:** delete the merged branch; start the next epic clean (`/clear`).
