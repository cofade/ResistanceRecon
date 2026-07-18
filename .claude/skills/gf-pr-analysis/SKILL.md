---
name: gf-pr-analysis
description: Load when reviewing or triaging an EXISTING Genome Firewall pull request (someone else's, or one handed to you) rather than authoring one — fetch its metadata and diff, run every locally runnable gate, check the safety invariants and the change-type doc matrix, and emit a falsifiable manual-test plan. Distinct from the senior-reviewer agent (adversarial architecture review) and gf-validation-and-qa (evidence standards).
user_invocable: true
---

# Genome Firewall — PR Analysis

Analyze an existing PR into an actionable picture: what it changes, whether the gates pass, whether the safety invariants and doc duties hold, and exactly what a human should manually test. This is *analysis of a PR that exists*; for authoring your own change use `gf-change-control`.

## Procedure

1. **Fetch metadata & diff.** Read the PR body, linked issue/epic, and the diff (cloud: `mcp__github__pull_request_read` / `pull_request_read` for files + `get_pull_request_diff`; local: `gh pr view <PR#>` / `gh pr diff <PR#>`). Note whether it is a **draft** (it should be until the user confirms manual testing).
2. **Run every locally runnable gate** against the branch: `uv run pytest` (cov ≥ 80) · `ruff check` + `ruff format --check` · `mypy --strict` · `bandit -r src/ --severity-level high` · `python scripts/check_import_boundary.py`. Report actual output, not "should pass".
3. **Check the safety invariants** (`gf-architecture-contract`): no LLM influence on a verdict; no train/test leakage; disclaimer on every report path; no raw dicts across boundaries; annotation stays behind the envelope. Any breach → escalate as P0 to the author/user.
4. **Check the change-type doc matrix** (`gf-docs-and-writing`): are the required docs + ADR + `ground-truth/decisions.jsonl` entry present for this change type?
5. **Check the integration-test obligation** (`gf-validation-and-qa`): does the user story ship its end-to-end shape, or is it happy-path-only where a boundary workflow was available?
6. **Emit the manual-test plan** (below).
7. For an adversarial architecture/correctness pass, hand off to the **senior-reviewer** agent — this skill gathers evidence; the agent renders the P0/P1/P2 verdict.

## Manual-test plan format

A falsifiable checklist the user can run, each item **action → expected observable outcome**, e.g.:

- Upload the fixture FASTA in the demo → firewall table renders 5 drugs with a verdict + calibrated confidence each.
- Feed an OOD/novel genome → those drugs show NO-CALL, not a confident guess.
- Trigger an annotator/OpenAI outage → a structured 503 / graceful degraded path, and the disclaimer banner still shows.
- Open any report path → the lab-confirmation disclaimer is present and non-dismissible.

Include the golden path, the risk surfaces implied by *this* diff, and the safety invariants — and subtract what automated tests already cover so the human effort lands where it matters.

## When NOT to use this skill

- Authoring your own change → `gf-change-control`.
- The adversarial architecture/severity verdict → the `senior-reviewer` agent.
- What counts as sufficient evidence in general → `gf-validation-and-qa`.
