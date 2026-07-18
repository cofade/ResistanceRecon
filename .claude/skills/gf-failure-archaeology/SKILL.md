---
name: gf-failure-archaeology
description: Load before changing an existing Genome Firewall subsystem, or when a behavior looks wrong/weird and you suspect it might be intentional. A quirk may be a deliberate scar from a past incident — check the record before "fixing" it. Points to where past decisions and incidents live (ground-truth/decisions.jsonl, ADRs, risks §11, debug-verbose case studies, Known AI Pitfalls) and how to record a new one.
user_invocable: true
---

# Genome Firewall — Failure Archaeology

Before you change something that looks odd, find out whether it's odd on purpose. This project keeps an explicit institutional memory precisely so an agent session doesn't re-introduce a bug a prior session paid to fix. Consult it first; a "cleanup" that reverts a scar is a regression.

## Where the memory lives

| Source | What it records |
|---|---|
| `ground-truth/decisions.jsonl` | Every notable human/agent decision — the *why* behind a choice, with `origin` and any ADR link |
| `Documentation/09-architecture-decisions/` | The durable architecture decisions and their Consequences/Addenda |
| `Documentation/11-risks-and-technical-debt/README.md` | Top risks + accepted technical debt (e.g. single grouped split for the MVP, thin KB → statistical-only evidence) |
| `CLAUDE.md` → Known AI pitfalls | Symptom → root cause → prevention, one entry per non-obvious trap |
| `.claude/skills/debug-verbose/SKILL.md` | Case studies: Symptom → Instrumentation → Root cause → Fix → Prevention |

## Before changing a subsystem

1. `grep` the subsystem's name/terms across the sources above.
2. Read the relevant ADR (and any Addenda) — the Consequences section often explains the "weird" shape.
3. Check Known AI Pitfalls and debug-verbose case studies for a matching symptom.
4. If the behavior is a documented scar, propose an **addendum** or a new ADR, not a silent reversal — and confirm with the user.
5. If it is genuinely a bug, fix it *and* record it (below) so the next session inherits the lesson.

## Known scars & standing traps (seed — extend as they occur)

- **LLM writing a verdict.** An LLM narrative once could state a verdict the model didn't produce (root cause: a verdict field on an LLM schema). Prevention: LLM schemas carry no verdict/confidence field; import-boundary + schema tests enforce it. Do not "simplify" by letting the narrator compute a verdict.
- **Inflated held-out accuracy.** Near-identical clonal genomes split across train/test. Prevention: homology-aware grouped split + an explicit no-leakage test. Do not switch to a plain random split for convenience.

## Recording a new failure (same session)

- Add a **Known AI Pitfall** to `CLAUDE.md` (bold rule → symptom → root cause → prevention).
- Add a **debug-verbose case study** if you instrumented to find it.
- Add a risk/technical-debt row in `Documentation/11-*` if it leaves standing debt.
- Append a `ground-truth/decisions.jsonl` line, and pin the fix with a regression test.

## When NOT to use this skill

- Actively instrumenting a live bug right now → `debug-verbose`.
- Where new documentation belongs / house style → `gf-docs-and-writing`.
- Whether a change is *allowed* by the invariants → `gf-architecture-contract`.
