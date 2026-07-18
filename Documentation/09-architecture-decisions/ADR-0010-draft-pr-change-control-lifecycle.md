# ADR-0010 — Draft-PR change-control lifecycle & manual-test sovereignty

- **Date:** 2026-07-18
- **Status:** Accepted
- **Origin:** Agent-proposed / human-approved (issue #35 process transfer).

## Context

The EPIC-0 scaffold had feature-branch + conventional-commit + senior-reviewer discipline, but the *end* of a change was under-specified: a pushed branch or an ordinary PR, merged once tests were green. The reference project (matured over many PRs) shows that automated green and independent review are necessary but **not sufficient** — a human manually testing the built system repeatedly overturned reviewed, green work. This must be the standing rule *before* EPIC 1–2 implementation accelerates, so every later agent session operates under it from the first line of real code. This is a "choosing between non-trivial approaches" ADR trigger.

## Decision

The mandatory lifecycle for every change (`gf-change-control`, `CLAUDE.md` Workflow, `finalize-epic`):

1. **Plan Mode** first for any non-trivial change — read the issue/acceptance criteria + roadmap + ADRs + arc42, analyze existing code, propose the smallest viable design, surface ≥1 alternative + failure modes, agree with the user, then implement.
2. **Feature branch** for every change (code, docs, CI, refactor); never commit to `main`.
3. **Every user story ships an end-to-end integration test** — no merge without it.
4. All **quality gates** green, then a **fresh-worktree senior-reviewer pass**, re-run until no P0/P1 remain.
5. **A draft PR is the normal end state**, carrying a falsifiable manual-testing checklist.
6. **Manual testing is sovereign:** the PR stays draft until the user *explicitly* confirms manual testing passed; only then mark ready and merge. Dropping a feature that fails manual testing is a legitimate outcome.
7. **Evidence hierarchy** (weakest → sovereign): green CI < full local gates < independent senior review < manual testing.

## Alternatives considered

- **Keep "green + reviewed → merge"** — rejected: it treats automated signals as sufficient, the exact failure the reference project's history refutes.
- **Require manual testing but merge non-draft** — rejected: draft status is the machine-checkable signal that the sovereign gate has not yet been cleared.

## Consequences

- (+) The user's manual test is an explicit, non-skippable gate; agents cannot self-approve a merge.
- (+) Integration-test-per-story and the doc-update matrix are enforced by the senior-reviewer and the PR template.
- (−) Slightly slower merges; acceptable for a safety-adjacent bio-ML tool where a confidently-wrong verdict is the danger.
- Files: `CLAUDE.md`, `AGENTS.md`, `.claude/skills/finalize-epic/SKILL.md`, `.claude/skills/gf-change-control/SKILL.md`, `.claude/agents/senior-reviewer.md`, `.github/pull_request_template.md`.
