---
name: "🔧 Task"
about: A unit of work under an epic (maps to a feature branch)
title: "[<EPIC>] <short title>"
labels: [task]
---

## Goal

<what this task delivers, in one or two sentences>

## Acceptance criteria

- [ ] ...
- [ ] Quality gates green (pytest cov≥80, ruff, mypy strict, bandit, import-boundary)
- [ ] Docs/ADR updated if triggered; decision logged in `ground-truth/decisions.jsonl`

## Notes / references

- arc42 / research-findings: ...
- Golden rules that apply: LLM never predicts · defensive by construction · no train/test leakage · disclaimer on every report
