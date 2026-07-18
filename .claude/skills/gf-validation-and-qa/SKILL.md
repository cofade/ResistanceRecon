---
name: gf-validation-and-qa
description: Load when deciding what evidence a Genome Firewall change needs — test authoring, completion criteria, PR readiness, or "is this proven?". Defines the evidence hierarchy, the test taxonomy, what counts as evidence for each surface (ingestion, features, training, calibration, conformal, report, API, UI), the mandatory safety-invariant tests, the per-user-story end-to-end integration-test shapes, and the documented limitations of each gate so green CI is never overclaimed as proof.
user_invocable: true
---

# Genome Firewall — Validation & QA

What counts as evidence, and what each gate does and does *not* prove. For the process around a change see `gf-change-control`; for how to run the gates see `gf-build-and-run`.

## Evidence hierarchy (weakest → sovereign)

1. **Green CI** — the assertions ran clean on a fresh machine. Pins only what tests cover.
2. **Full local quality gates** — pytest cov ≥ 80 + ruff + mypy strict + bandit + import-boundary.
3. **Independent senior review** — fresh eyes, P0/P1 resolved, re-reviewed after fixes.
4. **Manual testing by the user** — **sovereign**. Nothing merges without it.

Never present a lower tier as proof of a higher claim. "CI is green" ≠ "correct" — it means the assertions someone thought to write passed.

## Test taxonomy

| Kind | Question it answers | Marker/home |
|---|---|---|
| **Unit** | Does this function do the right thing on representative + edge inputs? | `tests/`, fast, no I/O |
| **Integration (end-to-end)** | Does a realistic boundary workflow produce the right contract? | `@pytest.mark.integration`, MockAnnotator |
| **Contract** | Do Pydantic schemas / the `{ok, source, error}` envelope / `feature_schema.json` version hold across a boundary? | schema round-trip tests |
| **Safety-invariant** | Are the non-negotiables structurally enforced? | see below — these are P0 if absent |
| **Security** | Bandit high clean; no committed secrets; safe subprocess/Docker/path handling | `bandit`, targeted tests |
| **Manual** | What nobody thought to assert — the user drives the real flow | PR manual-testing checklist |

## What counts as evidence, per surface

- **Data ingestion (EPIC 1):** a fixture BV-BRC table → normalized labels; assert only `evidence == 'Laboratory Method'` rows survive, the min-n gate (≥ 20 R and ≥ 20 S per drug else "insufficient data" no-call) fires, and the persisted dataset contract validates.
- **Feature construction (EPIC 2):** a FASTA fixture → `MockAnnotator` → feature vector that matches the versioned `feature_schema.json`; assert unknown/extra genes are handled, and schema-version mismatch is caught at inference.
- **Model training (EPIC 3):** trains on a grouped fold; assert the deterministic target gate is authoritative where it fires; assert artifacts are reproducible.
- **Calibration:** reliability measured (Brier + reliability curve) on a grouped (leakage-free) calibration fold; `cv='prefit'`.
- **Conformal prediction:** set → verdict mapping is exact: `{S}`→work, `{R}`→fail, `{S,R}`→ambiguous no-call, `{}`→novel/OOD no-call. Assert the mapping and the alpha (default 0.10) behavior.
- **Report generation (EPIC 4):** a prediction → a complete report whose `evidence_category` honestly separates KNOWN_MECHANISM from STATISTICAL_ASSOCIATION and that carries the disclaimer.
- **API behavior (EPIC 6):** request → structured response; an external-tool failure surfaces as a structured 503 from an `{ok:false}` envelope, not a stack trace.
- **UI behavior (EPIC 6):** upload/demo flow renders the verdict, evidence, and the non-dismissible disclaimer banner.

## Mandatory safety-invariant tests (P0 if absent)

- **Mocked-annotator end-to-end** test for the deterministic path (works with no Docker, no OpenAI key).
- **No leakage** across the homology-aware split: an explicit test that no genome group spans train and test.
- **Disclaimer presence** on *every* report path (schema validator + reviewer + UI) — a path that can emit a report without it fails.
- **LLM cannot alter verdict/confidence:** the import-boundary test passes *and* no LLM output schema carries a verdict/confidence/SIR field.
- **OOD / no-call:** empty or novel evidence yields a no-call, never a confident guess.
- **Calibration, evidence-category, and structured-error** tests as above.

## The 7 end-to-end integration-test shapes (one per user-story family — no merge without it)

1. **Data pipeline:** fixture data → normalized labels → persisted dataset contract.
2. **Reader:** FASTA fixture → MockAnnotator → feature vector.
3. **Predictor:** feature vector → target gate / model / calibration / conformal → verdict.
4. **Report:** prediction → complete report with evidence + disclaimer.
5. **LLM:** frozen report → narrative/reviewer → accepted, or fail-closed deterministic template.
6. **API:** request → structured response / error envelope.
7. **UI:** upload/demo flow → rendered verdict / evidence / disclaimer.

A feature is not mergeable with only happy-path unit tests when a realistic boundary workflow is available.

## Limitations of each gate (do not overclaim)

- **Coverage ≥ 80%** measures lines executed, not correctness — a fully-covered wrong branch is still wrong.
- **mypy strict** catches type mismatches, not logic or leakage.
- **bandit high** catches known insecure patterns, not design flaws or a leaked key already in history.
- **import-boundary** proves `predictor/features/reader` don't `import llm`; it does **not** prove an LLM value never reaches a verdict by another route — that needs the schema + reviewer tests too.
- **MockAnnotator** proves the pipeline shape, not that real AMRFinderPlus output matches the mock — periodically re-validate fixtures against a real run (`gf-data-and-annotation`).
- **Green CI** is the weakest tier. Manual testing is what merges the PR.
