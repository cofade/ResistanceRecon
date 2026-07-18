---
name: gf-architecture-contract
description: Load when designing a Genome Firewall feature or asking "is this allowed?" — anything touching the LLM boundary, the deterministic prediction path, Pydantic module boundaries, the lab-confirmation disclaimer, evidence categories, no-call semantics, or the annotation envelope. Carries the golden rules as enforceable invariants, a decision aid for allowed vs forbidden, and a digest of the ADRs that fix the architecture.
user_invocable: true
---

# Genome Firewall — Architecture Contract

The invariants that make this tool trustworthy. These are not style preferences — a breach is a safety defect. When a design would cross one, the design is wrong, not the rule. Golden-rule detail lives in `Documentation/08-crosscutting-concepts/README.md`.

## The invariants

1. **The LLM never predicts.** Every work/fail/no-call verdict and its confidence come *only* from the deterministic `predictor/` pipeline (per-antibiotic LR + sigmoid calibration + conformal). LLM output is never a model input. `predictor/`, `features/`, `reader/` import nothing from `llm/` — enforced by `scripts/check_import_boundary.py`. No LLM output schema carries a verdict/confidence/SIR field. **Any LLM path that can influence a verdict is P0.** (ADR-0006)
2. **Defensive by construction.** The system analyzes genomes; it never designs, modifies, synthesizes, or optimizes an organism. No sequence-writing capability may be added, ever.
3. **Ground Truth First — KNOWN vs STATISTICAL.** A deterministic gene/mutation KB hit (`KNOWN_MECHANISM`) is never conflated with a model/SHAP signal (`STATISTICAL_ASSOCIATION`). The `evidence_category` field and honest wording carry the distinction. Describing a statistical signal as a proven cause is P0/P1.
4. **The lab-confirmation disclaimer is on every report path**, enforced at three points: the Pydantic validator, the LLM-reviewer check, and the non-dismissible UI banner. A path that can emit a report without it is P0.
5. **No raw dicts across module boundaries.** Use the Pydantic schemas; validate all external input at the boundary.
6. **AMRFinderPlus runs only via Docker/WSL2**, isolated behind `annotation/` returning an `{ok, source, error}` envelope. Never a Python import; never in CI (tests use `MockAnnotator` + committed fixture TSVs). (ADR-0002)

## No-call semantics (the abstention contract)

Conformal set → verdict mapping is exact and must never be widened silently:

| Conformal set | Verdict |
|---|---|
| `{S}` | LIKELY TO WORK |
| `{R}` | LIKELY TO FAIL |
| `{S, R}` | NO-CALL (ambiguous) |
| `{}` | NO-CALL (novel / OOD) |

Also no-call: below the per-drug min-n gate ("insufficient data"), or when the deterministic target gate and model conflict in a way policy defines as abstention. Default alpha 0.10 (ADR-0004, ADR-0005).

## "Is this allowed?" decision aid

- Add a field to an LLM output schema that carries a verdict/confidence/SIR → **No** (invariant 1).
- Have `features/` or `predictor/` read anything the LLM produced → **No** (invariant 1).
- Import AMRFinderPlus as a Python library, or shell out to it inside a test → **No** (invariant 6).
- Emit a report/UI view without the disclaimer, "just for an internal path" → **No** (invariant 4).
- Pass a plain `dict` between modules instead of a schema → **No** (invariant 5).
- Add any capability that writes/edits/optimizes a sequence → **No** (invariant 2).
- Widen a conformal set or downgrade a no-call to a confident call to "improve" coverage numbers → **No** (no-call contract).
- Add a new dependency / data source / calibration-or-split change / any LLM-boundary change → allowed, **but requires an ADR** (`gf-docs-and-writing`).

## ADR digest

0001 self-sourced BV-BRC lab-AST data · 0002 AMRFinderPlus via pinned Docker/WSL2 · 0003 per-antibiotic L2 logistic regression · 0004 sigmoid calibration + conformal no-call · 0005 homology-aware grouped split · 0006 LLM boundary (RAG/reviewer/report only) · 0007 Streamlit + FastAPI · 0008 K. pneumoniae first · 0009 versioning & release control · 0010 draft-PR lifecycle & manual-test sovereignty. Read the ADR before touching what it fixes; propose an addendum rather than a silent reversal.

## When NOT to use this skill

- The process around a change (branch/PR/gates) → `gf-change-control`.
- What evidence/tests a change needs → `gf-validation-and-qa`.
- Why a past decision was made / prior incidents → `gf-failure-archaeology`.
