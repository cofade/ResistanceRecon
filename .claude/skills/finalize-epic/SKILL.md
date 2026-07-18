---
name: finalize-epic
description: End-of-epic/issue wrap-up — quality gates, fresh-worktree senior review, commit, push, DRAFT PR with a manual-testing checklist, then STOP for the user's manual testing before ready/merge; plus roadmap update, ground-truth decision log, branch cleanup. Assumes the code is approved and local tests pass. Load `gf-change-control` for the full lifecycle and rationale.
user_invocable: true
argument: "Epic/issue id and title, e.g. 'EPIC-3 Predictor: calibration + conformal'"
---

# Finalize Epic / Issue

Run the full post-approval wrap-up for a completed unit of work. All issues found during implementation must already be documented in the arc42 docs before this step. This skill is the mechanical end of the lifecycle in `gf-change-control` — do not re-derive its steps from memory.

## Operating rules

- Do not finalize from `main`; work from the feature branch (`feat/<epic>-<slug>`).
- Before opening the PR, run an independent review via `.claude/agents/senior-reviewer.md` on a **fresh worktree/diff vs `main`**. Fix every P0/P1, then **re-run until the review is clean** — a review of the original is not a review of the fix.
- **The PR is opened as a DRAFT and stays draft until the user confirms manual testing passed.** Automated green + clean review are necessary but never sufficient; manual testing is sovereign.
- **Never mark ready or merge without the user's explicit confirmation.** Ask before any irreversible remote action (mark-ready, merge, delete-branch) that is not already approved.
- Never create git tags manually. Release automation is **deferred** — there is no `release.yml` yet (see `gf-change-control` and ADR-0009). When it lands, wait on the release by a **tag state transition**, never by grepping dates.
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
3. **Independent review (fresh worktree):** launch the `senior-reviewer` agent on the diff vs `main`; treat the result as an input, not a rubber stamp. Fix every P0/P1, re-run affected gates, and **re-run the reviewer until it is clean**.
4. **Log the decision(s):** append entries to `ground-truth/decisions.jsonl` for anything ADR-worthy (in the same session); write/update the ADR if triggered; update docs per the change-type matrix (`gf-docs-and-writing`).
5. **Update `Documentation/roadmap.md`** (tick the epic; note what shipped).
6. **Commit** on the feature branch with a conventional message: `feat(<scope>): <description>`.
7. **Push:** `git push -u origin feat/<epic>-<slug>`.
8. **Open a DRAFT PR** — `gh pr create --draft` (cloud sessions: `mcp__github__create_pull_request` with `draft: true`). The body follows `.github/pull_request_template.md`: Summary, automated-test results, senior-reviewer result + re-review status, a **falsifiable manual-testing checklist** (step/command → expected observable outcome), documentation/ADR/ground-truth updates, safety invariants, known limitations, and the WOZCODE footer. Add it to the Project board manually if needed: `gh project item-add 3 --owner cofade --url <pr-url>`. **Never open a non-draft PR.**
9. **Gate on CI (state transition):** `gh pr checks <PR#> --watch --fail-fast`; never merge on red.
10. **STOP for manual testing.** The PR stays draft. The user runs the manual-testing checklist. Only on their **explicit confirmation** that it passed: mark ready (`gh pr ready`) and merge (`gh pr merge --squash --delete-branch`). If manual testing fails, fix on the same branch, re-run steps 2–9 (including a fresh senior-reviewer pass on the delta), and keep the PR draft — dropping the feature is a legitimate outcome.
11. **Clean up & clear context:** delete the merged branch; start the next epic clean (`/clear`). On explicit abandonment, `/clear` too.
