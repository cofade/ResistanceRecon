# ADR-0022 — In-process orchestrator for the demo UI (clarifying ADR-0007)

- **Date:** 2026-07-19
- **Status:** Accepted
- **Origin:** Agent-proposed / human-approved (EPIC 6 planning session, issues #7/#27/#28).
  Clarifies, does not reverse, ADR-0007.

## Context

ADR-0007 fixed the demo stack as "Streamlit front end + FastAPI backend" and described two
processes (Streamlit calling FastAPI). EPIC 6 has to turn that into running code, and two
concrete questions were open that ADR-0007 did not settle:

1. **Does the Streamlit UI reach the pipeline over HTTP, or in-process?** A literal reading of
   ADR-0007 has the UI POST to the FastAPI `/predict`. For a single-container Streamlit
   Community Cloud deploy that means a second process (uvicorn) must be kept alive alongside
   the Streamlit server, and the UI must handle the API being down — extra failure surface for
   no demo benefit, since both run on the same host.
2. **Where does the FASTA → verdict → report → narrative wiring live**, given `report.builder`
   was deliberately decoupled from `predictor.predict` (it consumes the `report.inputs`
   primitive contract, not `predict.py`)? Something has to bridge predictor primitives into
   `DrugPredictionInput` and call `build_report` → `narrate_report`. That glue must not go
   inside the frozen `report/` or `predictor/` packages.

## Decision

**One in-process orchestrator, two surfaces.** A new app-level module
`genome_firewall/service.py` owns the single `analyze_genome(...) -> NarrativeEnvelope`
pipeline (parse → annotate → features → `predict_genome` → adapter → `build_report` →
`narrate_report`). Both surfaces wrap it:

- **Streamlit (`ui/app.py`) calls `service.analyze_genome` directly, in-process** — no HTTP
  hop, no second process required for the demo. This is the deploy target.
- **FastAPI (`api/main.py`) wraps the same `service.analyze_genome`** as a separate,
  independently useful deliverable surface (`POST /predict`, `GET /health` / `/antibiotics` /
  `/model-card`), returning a `{ok:false,error}` envelope at 503 on any tool/pipeline failure
  and 422 on a malformed request — never a traceback.

**The adapter keeps the predictor sovereign.** `service.to_prediction_inputs` emits only
primitives (`ModelPrediction`, `ConformalSet`, top features, `insufficient_data`) into the
`report.inputs` contract; it asserts **no** verdict. `analyze_genome` still calls the sovereign
`predict_genome` (golden rule #1) up front — for its fail-loud DB/schema compatibility guard
and as the authoritative verdict source — while `build_report` re-derives the presentation
rows and applies the honest ADR-0020 evidence-category tagging that `predict.py`'s own output
does not carry. Because `build_report` checks `insufficient_data` *before* the gate while the
sovereign path checks the gate *first*, the adapter must evaluate the deterministic gate and
mark a drug `insufficient_data` **only when the gate does not fire** — otherwise an untrained
drug carrying a called known mechanism would collapse to a `no_signal` no-call in the report
while `predict_genome` forces `likely_to_fail` (a safety divergence caught in senior review;
see §11.4). A safety-invariant test (`tests/service/test_verdict_reconciliation.py`) pins the
two paths to agree on **verdict + calibrated confidence + conformal set** across the model,
gate-fired, empty-set, and untrained-gate-firing branches. It deliberately does **not** assert
`evidence_category` equality: the two paths differ there *by design* (predict.py tags model rows
`statistical_association`; `build_report` applies the stronger ADR-0020 KNOWN-vs-STATISTICAL
rollup) — that divergence is the intended benefit of routing the report through `build_report`,
not a drift. The ~5 extra logistic-regression evaluations per genome this costs are negligible.

**Bundled-demo vs upload.** The UI/API default to a `MockAnnotator` over committed demo
fixtures so the demo works offline with no Docker (golden rule #6); real AMRFinderPlus is used
only when `GF_USE_DOCKER=1` is set explicitly, and an uploaded arbitrary FASTA is honestly
gated behind that.

Rejected — **UI over HTTP (two processes):** more moving parts and failure surface for a
single-host demo, with no benefit; the FastAPI surface still exists for anyone who wants the
network API. Rejected — **putting the orchestrator inside `report/` or `predictor/`:** both are
frozen foundation; app-level wiring does not belong in them, and it would blur the
report-decoupled-from-predict boundary those packages were designed around.

## Consequences

- (+) A robust one-click demo (single Streamlit process, offline-safe) plus a clean, reusable
  HTTP API — both provably the same pipeline (one `service.analyze_genome`).
- (+) Golden rule #1 is preserved and made airtight: predictor stays the sole verdict source,
  the report path is pinned to it by test, and no LLM output influences a verdict.
- (+) The disclaimer is carried on every branch (deterministic / accepted / rejected /
  disabled) and every UI view and API report response.
- (−) `analyze_genome` runs the model twice (once in `predict_genome`, once in the adapter's
  primitive extraction) — a deliberate, negligible cost for keeping predictor sovereign and
  the report honestly ADR-0020-tagged, rather than reconstructing `probability_resistant` by
  inverting confidence (fragile) or skipping `build_report` (less honest evidence).
- (−) The real-AMRFinderPlus upload path and the real-OpenAI narrative path are not exercised
  in CI (Docker/keys forbidden there) — both are user manual-test items; CI covers the mock
  paths end-to-end.
- One dependency is made explicit: `httpx>=0.27` is added to the `dev` group (FastAPI's
  `TestClient` needs it for the ASGI transport). It is a test-only, already-transitive dep
  pinned for CI robustness — not a new runtime dependency.
- Pinned by `tests/service/*`, `tests/api/*`, `tests/ui/*`. Does not change the LLM boundary
  (ADR-0006) or any prediction method.
