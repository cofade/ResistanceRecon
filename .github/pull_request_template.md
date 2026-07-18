## Summary

- <what changed and why, in bullets>

## Test plan

- [ ] `uv run pytest` (coverage ≥ 80)
- [ ] `ruff check` + `ruff format --check` + `mypy --strict` + `bandit` + `check_import_boundary.py` green
- [ ] senior-reviewer run; P0s addressed
- [ ] Docs/ADR updated if triggered; `ground-truth/decisions.jsonl` appended

## Safety invariants (confirm none violated)

- [ ] The LLM path cannot influence a verdict/confidence (no verdict field on LLM schemas; `predictor/` imports no `llm/`)
- [ ] No train/test leakage across the homology-aware split
- [ ] The lab-confirmation disclaimer is present on every report path

🧙 Built with [WOZCODE](https://wozcode.com)
