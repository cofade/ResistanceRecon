---
name: gf-change-control
description: Load BEFORE starting ANY change to Genome Firewall — feature, bug fix, refactor, docs, or CI — and whenever you are about to branch, commit, open a PR, mark a PR ready, merge, or you are wondering whether an action (tagging, pushing to main, merging without user sign-off, skipping a test) is allowed. Explains how changes are classified, every non-negotiable gate and why it exists, the draft-PR lifecycle and manual-test sovereignty, the versioning/release deferral, and a start-to-finish checklist. If you are unsure whether a gate applies, it does — read this first.
user_invocable: true
---

# Genome Firewall — Change Control

How changes enter this repository, which gates they pass, and why. This is *process*, not technique: for *how to run* things see `gf-build-and-run`; for *what evidence counts* see `gf-validation-and-qa`; for *which docs to touch* see `gf-docs-and-writing`. Nothing here may be routed around.

Default branch `main`; repo `cofade/ResistanceRecon`. Version source of truth: `src/genome_firewall/__init__.py:__version__` (see ADR-0009). Release automation is **deferred** — there is no `release.yml` yet.

## 1. Classify the change

| Class | Source of truth | Branch | Commit prefix |
|---|---|---|---|
| Epic / user story | `Documentation/roadmap.md` (read the acceptance criteria first) | `feat/<epic>-<slug>` | `feat(<scope>): ...` |
| Bug fix / follow-up | GitHub issue `#NNN` | `fix/<nnn>-<slug>` | `fix(<scope>): ...` |
| Docs / CI / chore | — | `docs/<slug>`, `ci/<slug>`, `chore/<slug>` | `docs:` / `ci:` / `chore: ...` |

Everything a change adds must eventually be reflected in the arc42 docs and possibly an ADR — see `gf-docs-and-writing` for the duty matrix (it mirrors the table in `CLAUDE.md`).

## 2. The non-negotiables (rule → why)

1. **Never commit directly to `main`.** Branch first, always — even for a one-file doc fix. `main` is the integration line; it must stay green and reviewable.
2. **Plan Mode before any non-trivial change.** Read the issue/acceptance criteria + roadmap + ADRs + arc42 chapter, analyze the existing code, propose the smallest viable design, surface ≥1 alternative and its failure modes, agree with the user, then implement. This stops technically-correct-but-excessive or unsafe agent designs.
3. **The safety invariants are P0.** No LLM path may influence a verdict/confidence; no train/test leakage across the homology-aware split; the lab-confirmation disclaimer on every report path. See `gf-architecture-contract`. The import-boundary check (`scripts/check_import_boundary.py`) is a hard gate.
4. **Every user story ships an end-to-end integration test.** No merge without it — the seven per-story shapes live in `Documentation/08-crosscutting-concepts/README.md` (canonical) and are mirrored in `gf-validation-and-qa`.
5. **All quality gates green before review:** `uv run pytest` (cov ≥ 80) · `ruff check` + `ruff format --check` · `mypy --strict` · `bandit -r src/ --severity-level high` · `check_import_boundary.py`.
6. **senior-reviewer pass before the PR — and re-run after fixes.** Fresh worktree/diff vs `main`. Fix every P0/P1, then re-run until clean; a review of the original is not a review of the fix. Reviews are inputs, not oracles — verify each finding against the code (in both directions).
7. **Every coding job ends with a DRAFT PR — and stays draft until the user says so.** Push the branch and open with `gh pr create --draft` (cloud: `mcp__github__create_pull_request`, `draft: true`). Never stop at "branch pushed". Never open a non-draft PR.
8. **Manual testing is sovereign.** Automated green + a clean review are necessary, never sufficient. The PR carries a falsifiable manual-testing checklist; it stays draft until the user *explicitly* confirms manual testing passed. Only then: mark ready and merge. If the *design* fails manual testing, dropping the feature is a legitimate outcome.
9. **Ask before irreversible remote actions** (mark-ready, merge, delete-branch, force-push) that are not already approved.
10. **Never create git tags manually.** Release automation is deferred; when it lands, CI owns tags/versions (§4). Observe CI/release state by **transition**, never by grepping dates.

## 3. Evidence hierarchy (weakest → sovereign)

Green CI < full local gates < independent senior review < **manual testing (user-owned)**. Never overclaim a lower tier as proof; green CI means "the assertions someone wrote passed", not "correct". Full detail: `gf-validation-and-qa`.

## 4. Versioning & release (deferred)

- **Source of truth:** `src/genome_firewall/__init__.py:__version__`; `pyproject.toml` reads it dynamically via hatch (`[tool.hatch.version]`). Do not add a second static version — the duplication is the bug this design removes. See ADR-0009.
- **No manual tags.** When release automation is enabled it will trigger on push to `main`, compute the next version from the latest tag + the merged PR's semver label (default patch), and be the only thing that creates tags. Until then, do not tag.
- **State transitions, not dates.** When a release workflow exists, capture the top tag before merging and poll until it *changes*; a date match cannot detect a failed release.

## 5. Checklist — start to finish

| # | Step | Gate |
|---|---|---|
| 1 | Classify (§1); read the source of truth; **Plan Mode** | Don't code from the title |
| 2 | `git checkout -b feat/<epic>-<slug>` | Never on `main` (2.1) |
| 3 | Implement with type hints; keep raw dicts off module boundaries (Pydantic) | `gf-architecture-contract` |
| 4 | Write the end-to-end integration test | Mandatory (2.4) |
| 5 | Quality gates all green | 2.5; how-to in `gf-build-and-run` |
| 6 | Update docs + append `ground-truth/decisions.jsonl` (same session); ADR if triggered | `gf-docs-and-writing` |
| 7 | senior-reviewer pass; fix P0/P1; re-run until clean | 2.6 |
| 8 | Commit `feat(<scope>): ...`; push; open **draft** PR with manual-testing checklist | 2.7 |
| 9 | Wait for CI green (`gh pr checks <PR#> --watch --fail-fast`) | Never merge on red |
| 10 | **STOP.** User manual-tests. On explicit confirmation only: `gh pr ready` → `gh pr merge --squash --delete-branch` | 2.8, 2.9 |
| 11 | Delete local branch; `/clear` | |

The mechanical wrap-up (steps 6–11) is the `finalize-epic` skill — invoke it rather than re-deriving.

## When NOT to use this skill

- Running app/tests/builds → `gf-build-and-run`.
- What proof a claim needs / the manual-test checklist contents → `gf-validation-and-qa`.
- The wrap-up sequence itself → `finalize-epic`.
- Which docs to touch → `gf-docs-and-writing`.
- Why the code is shaped this way (invariants, ADR digest) → `gf-architecture-contract`; past incidents → `gf-failure-archaeology`.
