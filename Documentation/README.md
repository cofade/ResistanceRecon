# Genome Firewall — Documentation

arc42-structured architecture & research documentation for **Genome Firewall** (repo: ResistanceRecon), a strictly-defensive AI decision-support prototype that predicts antibiotic response from a *Klebsiella pneumoniae* genome.

> **Documentation discipline (project golden rule):** every research or design finding is written here in the same session it is produced. No finding lives only in chat. This is both good engineering practice and the data-collection mechanism for the *Sustainable Agentic Software Engineering* paper this project doubles as a case study for.

## arc42 chapters

| # | Chapter | Location |
|---|---|---|
| 1 | Introduction & goals | [`01-introduction-and-goals/`](01-introduction-and-goals/) — incl. [`prd.md`](01-introduction-and-goals/prd.md) (plan) and [`challenge-brief.md`](01-introduction-and-goals/challenge-brief.md) (verbatim challenge PDF) |
| 2 | Architecture constraints | [`02-constraints/`](02-constraints/) |
| 3 | Context & scope | [`03-context-and-scope/`](03-context-and-scope/) |
| 4 | Solution strategy | [`04-solution-strategy/`](04-solution-strategy/) |
| 5 | Building-block view | [`05-building-block-view/`](05-building-block-view/) |
| 6 | Runtime view | [`06-runtime-view/`](06-runtime-view/) |
| 7 | Deployment view | [`07-deployment-view/`](07-deployment-view/) |
| 8 | Crosscutting concepts (golden rules) | [`08-crosscutting-concepts/`](08-crosscutting-concepts/) |
| 9 | Architecture decisions (ADRs 0001–0008) | [`09-architecture-decisions/`](09-architecture-decisions/) |
| 10 | Quality requirements | [`10-quality-requirements/`](10-quality-requirements/) |
| 11 | Risks & technical debt | [`11-risks-and-technical-debt/`](11-risks-and-technical-debt/) |
| 12 | Glossary | [`12-glossary/`](12-glossary/) |

## Other documents

| Doc | Purpose |
|---|---|
| [`roadmap.md`](roadmap.md) | Epic/milestone roadmap |
| [`research-findings/`](research-findings/) | Web-grounded research + reuse-grounded design (7 docs, with sources) |
| `MODEL_CARD.md` | Responsible-AI model card — *created in EPIC 7 (needs real metrics)* |
| `DATASHEET.md` | Dataset datasheet — *created in EPIC 7* |
| `reuse-inventory.md` | Which prior-project files we reuse — **local only, gitignored** (references private repos) |

## Provenance

The research in [`research-findings/`](research-findings/) was produced by a 7-agent web-grounded design workflow (4 research + 3 design). The verbatim structured output of every agent — including all source URLs — is persisted in the workflow journal at
`.claude/projects/…/subagents/workflows/wf_8772eb55-01b/journal.jsonl`
and transcribed faithfully into the research-findings documents. Each document lists its own sources.
