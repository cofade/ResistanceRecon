---
name: debug-verbose
description: Evidence-based debugging via targeted verbose instrumentation. Apply at the first sign of any non-obvious bug — before theorising. Grows with each bug fixed in this project.
user_invocable: true
argument: "Optional: short description of the bug or area to instrument"
---

# Verbose Debug Instrumentation

**Core principle:** stop theorising, start observing. For any non-trivial bug, first instrument the code so the actual runtime sequence prints to stdout, reproduce, and read what happened. Fix from evidence, not assumptions.

## When to apply (proactively)

- Behaviour differs from what the code appears to do.
- A model/calibration/conformal result is surprising (e.g. a genome that should be a clear resistant call comes back no-call, or vice versa).
- A feature vector doesn't line up with the trained `feature_schema.json`.
- The AMRFinderPlus envelope returns `ok=false` for an input you expect to work.
- A guard/condition seems correct but isn't firing.

## How to instrument

1. **Map the execution spine** from trigger to outcome (e.g. `parse -> annotate -> feature-build -> gate -> model -> conformal -> verdict`). Add a `print` at each node.
2. **Print at each node:** function name + key args; the exact values a condition reads; for the gate: which rule fired and the matched gene; for the model: the calibrated probability; for conformal: the prediction set; envelope `ok`/`error`; exit branch taken.
3. **Use `print` with a `[DEBUG]` prefix**, not `logging` (no config needed; grep-able):
   ```python
   print(f"[DEBUG predict] drug={drug} gate={gate_result} p_cal={p:.4f} conformal_set={cset}")
   ```
4. **Include a stack trace at "unexpected" call sites:** `import traceback; traceback.print_stack()`.
5. **Remove ALL `[DEBUG]` statements before committing** (a bandit/ruff check and the senior-reviewer will catch leftovers). Permanent diagnostics use `logging`.

## Case studies (append one per non-obvious bug fixed)

<!-- Format: Symptom -> Instrumentation -> Root cause -> Fix -> Prevention. Mandatory,
same session, no exceptions. The CANONICAL detailed log is Documentation/11-risks-and-technical-debt/
README.md §11.4; also mirror a quick line into CLAUDE.md "Known AI pitfalls" and pin a regression
test. See gf-failure-archaeology. -->

### Issue #45 — a percent token that exists only in the published narrative

- **Symptom:** the reviewer's deterministic pre-check reported a narrative as clean (`_PERCENT_RE.findall` on the validated prose = `[]`), yet the string actually published by `report/pipeline._flatten` contained an `88%` confidence token no check had seen.
- **Instrumentation:** printed `_PERCENT_RE.findall(...)` at two points — on `reviewer._section_prose(section)` (what the pre-check scans) and on `pipeline._flatten(section, report)` (what is published) — for a section whose per-drug narrative ended in a bare KB digit (`…identity 88`) followed by a caveat beginning `%`. Observed `[]` vs `['88']`: the differential is real and lives entirely in the newline join.
- **Root cause:** two guards checking a proxy. The pre-check scans a *differently-ordered* serialization (`summary, caveats, narratives`) than `_flatten` publishes (`summary, narratives, caveats, disclaimer`), and `_PERCENT_RE = (\d+(?:\.\d+)?)\s*%` — the `\s*` matches a newline, so `"88\n%"` forms an `88%` token across the join in the published order only.
- **Fix:** `_PERCENT_RE` → `(\d+(?:\.\d+)?)[^\S\r\n]*%` (intra-line); number validation moved per-component so each published unit is what is checked; `reviewer.published_percents_grounded` re-scans the FINAL flattened string with `pipeline.narrate_report` failing closed to the deterministic template on any ungrounded published percent.
- **Prevention:** a deterministic guard must scan the exact artifact it protects; where it can't, a fail-closed tripwire on the published string catches drift. Pinned by `tests/report/test_pipeline.py::test_flattened_output_forms_no_percent_the_precheck_missed` and `::test_tripwire_fails_closed_if_flatten_emits_an_ungrounded_percent`. See §11.4 (issue #45), ADR-0023.
