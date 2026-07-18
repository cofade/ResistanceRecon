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

_(none yet — add the first real case study here when it happens.)_
