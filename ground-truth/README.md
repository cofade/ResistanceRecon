# Ground Truth — Decision Log

This folder is the append-only record of how Genome Firewall was built with an AI agent. It is both good engineering hygiene (Layer 6 — Entropy Management) and the **primary data source for the *Sustainable Agentic Software Engineering* paper's case study**.

## Files

- **`decisions.jsonl`** — one JSON object per non-trivial decision. Fields:
  `date`, `decision`, `choice`, `rationale`, `adr` (ADR id or null), `origin`
  (`human` | `agent-proposed/human-approved` | `agent`), and optional `notes`.
- **`session-log-template.md`** — copy per work session to leave a parseable trace.

## Rule

Every ADR trigger and every notable agent/human decision appends an entry here **in the same session it happens** — not reconstructed at the end. Retroactive reconstruction loses the fine-grained decision trail that is the whole point.
