---
name: gf-docs-and-writing
description: Load when finishing ANY Genome Firewall change (docs are always owed — this project documents continuously), when writing an ADR, a risk/technical-debt entry, a research finding, a Known-AI-Pitfall, or a debug-verbose case study, when updating the roadmap or CLAUDE.md progress table, or whenever you are unsure WHERE a piece of knowledge belongs. Carries the canonical change-type→document matrix, ADR triggers, the ground-truth logging duty, the pre-merge doc-verification checklist, and house style.
user_invocable: true
---

# Genome Firewall — Docs & Writing

Every change must leave the docs better than it found them. Documentation is the project's institutional memory and the ground-truth for the Sustainable Agentic SE case study — no finding may live only in chat.

## Knowledge map

| Document | Path | Holds |
|---|---|---|
| arc42 chapters (12) | `Documentation/NN-*/README.md` | Architecture, runtime, quality, risks, crosscutting, glossary |
| ADR register | `Documentation/09-architecture-decisions/` | One `ADR-NNNN-*.md` per decision + an index README table |
| Roadmap | `Documentation/roadmap.md` | Epics / user stories + acceptance criteria |
| Glossary | `Documentation/12-glossary/README.md` | Domain terms |
| Risks & tech debt | `Documentation/11-risks-and-technical-debt/README.md` | Top risks + accepted debt |
| Research findings | `Documentation/research-findings/` | Bio + ML ground-truth with sources |
| Model card / datasheet | `Documentation/MODEL_CARD.md`, `Documentation/DATASHEET.md` | EPIC 7 (real metrics) |
| Decision log | `ground-truth/decisions.jsonl` | Append-only, one JSON object per decision |

## Mandatory change-type → document matrix (canonical)

`CLAUDE.md` carries a compact copy; this is the source of truth.

| Change | Required documentation |
|---|---|
| New module or package | `Documentation/05-building-block-view/` (black-box description) + the architecture map |
| Runtime / pipeline behavior | `Documentation/06-runtime-view/` (sequence diagrams) |
| New data source or preprocessing rule | ADR + `research-findings/` + risks + dataset datasheet (when it exists) |
| Model / split / calibration / conformal change | ADR + `10-quality-requirements/` + risks + model card + `ground-truth/decisions.jsonl` |
| New API / UI capability | runtime + deployment docs + acceptance criteria + manual test plan |
| New domain term | `Documentation/12-glossary/` |
| New security or safety issue | risks/technical debt + a test + ADR if architectural |
| Non-obvious bug | Known AI Pitfalls (`CLAUDE.md`) + risks + `debug-verbose` case study + regression test |
| Research / design finding | `Documentation/research-findings/` in the same session |

Before merge: verify the required docs are updated and cross-references (paths, ADR numbers, EPIC labels) are not stale.

## ADR triggers

Write an ADR (`Documentation/09-architecture-decisions/ADR-NNNN-<slug>.md`, and add a row to the index README) when: adding a dependency; a new bio data source; changing the calibration / conformal / split method; **any change to the LLM boundary**; or choosing between non-trivial approaches. Format: `# ADR-000N — Title`, then **Date, Status, Context, Decision, Consequences**. Prefer additive **Addenda** over rewrites once an ADR is Accepted.

## Ground-truth logging duty

Every ADR trigger and every notable agent/human decision appends one line to `ground-truth/decisions.jsonl` **in the same session it happens** — not reconstructed at the end. Fields: `date`, `decision`, `choice`, `rationale`, `adr` (id or `null`), `origin` (`human` | `agent-proposed/human-approved` | `agent`), optional `notes`. Append; never restructure existing lines.

## Pre-merge documentation checklist

- [ ] arc42 chapter(s) for this change type updated (matrix above).
- [ ] ADR written if triggered, and the index README row added.
- [ ] Glossary updated if a new domain term appeared.
- [ ] `ground-truth/decisions.jsonl` appended this session.
- [ ] Roadmap epic ticked / status noted.
- [ ] `CLAUDE.md` progress table current.
- [ ] Non-obvious bug → `debug-verbose` case study + Known AI Pitfall entry.
- [ ] Cross-references and paths verified (no dangling links).

## House style

- Docs are English; date-stamp volatile process facts so staleness is detectable.
- Every claim carries evidence: issue/PR numbers, test paths, file:line.
- Known AI Pitfall entries lead with a bold one-line rule, then symptom → root cause → prevention, and cite the pinning regression test.
- Never renumber existing ADR or FR IDs.
