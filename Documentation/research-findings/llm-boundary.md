# LLM / RAG Boundary & Responsible-AI Mapping

*Transcribed from the 2026-07-18 Genome Firewall design workflow (design agent D3). The LLM is structurally barred from the prediction path.*

## Principle

The LLM **never predicts**. Verdicts (LIKELY TO WORK / LIKELY TO FAIL / NO-CALL) and calibrated confidence are computed once, upstream of any LLM call, by the classical logistic-regression + calibration + conformal-prediction pipeline. The LLM's output Pydantic schemas contain **no** verdict/confidence/SIR-class field — there is nothing for an LLM to populate even under a prompt-injection attempt. The LLM only *explains* an already-final, frozen `GenomeReport`.

## Components

### GenomeReport / AMR schema layer
- **Purpose:** Pydantic-everywhere contracts (`extra="forbid"`) that make the boundary structurally enforceable, not merely prompt-enforceable. Includes `EvidenceItem.evidence_category: Literal['KNOWN_MECHANISM','STATISTICAL_ASSOCIATION']` and a mandatory disclaimer field with a `model_validator(mode='after')` that rejects any `GenomeReport` whose disclaimer text is missing or altered.
- **Reuse from:** `agentic-ai-challenge/schemas.py` (Literal enums, `extra='forbid'`, cross-field `model_validator`).
- **Paths:** `src/genome_firewall/schemas.py`

### LLM provider abstraction (OpenAI primary)
- **Purpose:** Provider-agnostic `LLMClient` Protocol + `Message`/`ToolSpec`/`LLMResponse` types, plus a new `OpenAIBackend` (structured outputs via `response_format`/`json_schema`) as the default in `factory.make_client()`. `MockLLMClient` reused unchanged so every LLM-touching path is deterministically testable in CI with zero API key.
- **Reuse from:** `agentic-ai-challenge/llm/{client,types,factory,errors}.py` + `MockLLMClient` (verbatim); `AnthropicBackend` kept as optional secondary.
- **Paths:** `src/genome_firewall/llm/openai_backend.py`, `factory.py` (adapted), `client.py`, `types.py`, `errors.py` (ported)

### Deterministic report builder (the fallback-of-record)
- **Purpose:** Assembles the final `GenomeReport` straight from the ML pipeline output (verdict, calibrated confidence, conformal no-call) + AMRFinderPlus hits, tags each `EvidenceItem` KNOWN_MECHANISM vs STATISTICAL_ASSOCIATION by deterministic KB-membership lookup, and injects the canonical disclaimer. **Must work end-to-end with zero LLM calls** — it IS the demo safety net.
- **Reuse from:** new; envelope/graceful-degradation from `EPOChallenge/src/epo_connectors/epo_tools.py`.
- **Paths:** `src/genome_firewall/report/builder.py`, `report/template.py.jinja`

### AMR-mechanism Evidence RAG (`kb/`)
- **Purpose:** Hybrid BM25+embedding+RRF retriever over a curated KB of AMR resistance mechanisms (CARD ARO descriptions, AMRFinderPlus reference-gene notes, review-article summaries). Given the detected genes, retrieves top-k cited chunks per gene to (a) enrich the report with citations and (b) supply the ground truth that lets an `EvidenceItem` be upgraded to KNOWN_MECHANISM. **The retriever never decides a verdict** — it returns text + provenance only.
- **Reuse from:** `agentic-ai-challenge/kb/{loader,chunker,retriever}.py` and `agents/retrieve.py`.
- **Paths:** `src/genome_firewall/kb/{loader,chunker,retriever}.py`, `kb/seed/`, `src/genome_firewall/agents/evidence_rag.py`

### Grounded NL report generator (LLM, prose only)
- **Purpose:** Turns the final `GenomeReport` + RAG citations into clinician-readable prose. Tool-forced output (`NLReportSection`: summary, per-antibiotic narrative, caveats, citations), `temperature=0`. Its input schema carries verdict/confidence as read-only context; its OUTPUT schema has no numeric verdict/confidence fields — narrative must reference values already present in the structured report, enforced downstream by the reviewer.
- **Reuse from:** `agentic-ai-challenge/agents/reason.py` (structured draft + `ClaimEvidence`: each sentence maps to a chunk_id + quote).
- **Paths:** `src/genome_firewall/agents/report_generator.py`

### LLM-as-Reviewer (groundedness gate)
- **Purpose:** Verifier that checks every claim in the generated NL report is supported by the structured `GenomeReport` fields or a cited RAG chunk, and explicitly checks the STATISTICAL_ASSOCIATION vs KNOWN_MECHANISM wording was not upgraded/blurred. Emits a tool-forced `ReportVerdict{grounding_score, per_claim[], overall_pass}`. `overall_pass=false` **blocks** the LLM narrative — the API falls back to the deterministic template and tags `review_status='llm_output_rejected'`.
- **Reuse from:** `agentic-ai-challenge/agents/verify.py` (LLM-as-judge) + `ClaimEvidence.quote` substring pre-check.
- **Paths:** `src/genome_firewall/agents/report_verifier.py`

### Confidence / no-call UI surfacing (guardrail, not LLM)
- **Purpose:** Deterministic rendering of reliability diagram + Brier score, per-split (incl. unseen-group) performance, and the no-call state — entirely from the ML pipeline's own outputs, never touched by an LLM. Confidence numbers shown are byte-identical to what the generator was given, so the verifier can trivially catch drift.
- **Reuse from:** `agentic-ai-challenge/confidence.py` (component-breakdown dict alongside the scalar).
- **Paths:** `src/genome_firewall/report/model_card.py`

### Human-oversight disclaimer enforcement
- **Purpose:** Canonical "confirm with standard lab testing" string lives as a module-level constant, asserted present by a Pydantic validator on `GenomeReport`, asserted present (verbatim substring) by `report_verifier`, and rendered as a non-dismissible banner above every result in Streamlit — **three independent enforcement points** so no single failure can drop it.
- **Reuse from:** `agentic-software-engineering` templates (Layer 6) + `schemas.py` validator pattern.
- **Paths:** `src/genome_firewall/constants.py`, `schemas.py` (validator)

## Boundary decisions

### LLM is structurally barred from the prediction path
**Choice:** LLM output schemas (`NLReportSection`, `ReportVerdict`) contain no verdict/confidence/SIR-class field at all. Verdicts + confidence are computed upstream by the classical LR + calibration + conformal pipeline and passed to the LLM only as immutable read-only context strings.
**Rationale:** Prompt instructions ("don't change the verdict") are advisory and break under adversarial/degenerate input; schema-level field absence is a structural guarantee that survives model upgrades, prompt drift, and jailbreaks — mirrors the closed-`Literal`/`extra='forbid'` discipline in `wscad_triage/schemas.py`.

### Evidence RAG is retrieval-only, never adjudicative
**Choice:** `evidence_rag` only fetches + cites KB chunks for genes AMRFinderPlus already detected; it never decides whether a gene is causally resistant. The KNOWN_MECHANISM vs STATISTICAL_ASSOCIATION tag is set by a deterministic set-membership check (detected gene present in the curated mechanism KB) in the report builder, before any LLM runs.
**Rationale:** Keeps the one output that most looks like "the AI's opinion" (a known-mechanism label) fully deterministic, reproducible, regression-testable, and auditable without re-running any LLM.

### LLM-as-Reviewer blocks publication (fail-closed)
**Choice:** `ReportVerdict.overall_pass=false` (any unsupported/mislabeled claim) causes the API to serve the Jinja2 deterministic template instead of the LLM narrative, and stamps `review_status='llm_output_rejected'` so the failure is visible.
**Rationale:** A reviewer that only logs a warning while still serving flagged text provides no real safety; failing closed to the deterministic path is what makes the gate load-bearing — and it's free because that path must exist as the no-API-key fallback anyway.

### Deterministic-first defense before the LLM judge
**Choice:** Before the reviewer's LLM call runs, a cheap non-LLM check (every value/drug name/number in the NL report must appear verbatim in the structured `GenomeReport` or a cited chunk) runs first and can reject outright.
**Rationale:** An LLM judging another LLM has a shared-failure-mode ceiling; a deterministic string/number-membership check catches the crudest, most consequential failure (a fabricated drug name or confidence number) without depending on the judge model.

### Provider choice: OpenAI primary, Anthropic swappable
**Choice:** `llm.factory.make_client()` defaults to `OpenAIBackend` (structured outputs) but keeps the `LLMClient` Protocol so Anthropic or Mock swap in via one settings flag with zero call-site changes.
**Rationale:** Matches the OpenAI-powered hackathon while preserving the provider-agnostic architecture; swap-testing against `MockLLMClient` keeps CI deterministic and key-free.

## Responsibility requirements → implementation

| # | Requirement | Implementation |
|---|---|---|
| 1 | **Defensive by construction** | No organism-generation/sequence-editing/synthesis path exists anywhere; FASTA is read-only input. Enforced by never importing a sequence-writing library, plus a golden principle in CLAUDE.md + ADR + ruff/bandit/grep pre-commit check. Structural absence > policy statement. |
| 2 | **Honest generalization** | `model_card.py` reports per-antibiotic performance on the homology-aware grouped split, broken out for held-out (unseen) genetic groups vs in-distribution; states exactly which species (K. pneumoniae at MVP) and antibiotics are covered, with an explicit "not covered" state. Surfaced in the Streamlit model-card view + a machine-readable coverage manifest on every API response. |
| 3 | **Calibrated confidence + no-call** | Confidence shown = calibrated (not raw) probabilities; reliability diagram + Brier on the held-out grouped split; conformal produces an explicit NO-CALL verdict (non-singleton or OOD prediction set) distinct from low-confidence, rendered with distinct styling; NO-CALL is first-class and the LLM must render it as-is, never smoothed into a soft "probably". |
| 4 | **Honest explanations (association vs mechanism)** | Every `EvidenceItem` carries `evidence_category` KNOWN_MECHANISM (deterministic KB-membership) or STATISTICAL_ASSOCIATION (SHAP/feature-importance the classifier weighted, with no curated-mechanism citation); UI renders distinct badges + separate headers ("Known resistance mechanisms" vs "Statistical signals — not confirmed mechanisms"); `report_verifier` flags any sentence describing a STATISTICAL_ASSOCIATION item with causal language ("causes", "confers"). SHAP importance is correlational within the model, not biological proof. |
| 5 | **Human oversight** | Canonical disclaimer ("This is decision support only — confirm every result with standard laboratory antimicrobial susceptibility testing before any clinical action") enforced at three independent points: Pydantic validator (structural), reviewer substring check (LLM-path), non-dismissible Streamlit banner (presentation). |

## Build order

1. `schemas.py`: `GenomeReport`, `AntibioticVerdict`, `EvidenceItem(evidence_category)`, `NLReportSection`, `ReportVerdict`, disclaimer constant + validator — ported from `wscad_triage/schemas.py` conventions.
2. `llm/{types,client,errors,factory}.py` ported verbatim + new `openai_backend.py`; `MockLLMClient` reused for CI.
3. Deterministic report builder (`report/builder.py` + Jinja2 template) — complete `GenomeReport` with zero LLM calls; MVP core AND guaranteed demo fallback; fully working + tested before any LLM code.
4. Seed the AMR-mechanism KB (CARD ARO descriptions, AMRFinderPlus reference notes, review summaries) as chunked JSON/markdown; port `kb/{loader,chunker,retriever}.py`; validate retrieval on canonical gene-name queries.
5. `evidence_rag` agent: retrieve + attach citations; deterministic KB-membership sets `evidence_category`.
6. `report_generator` agent (LLM): tool-forced `NLReportSection`, `temperature=0`, adapted from `agents/reason.py`.
7. `report_verifier` agent: deterministic substring/number pre-check, then adapted `agents/verify.py` judge; wire fail-closed gate to the template fallback.
8. FastAPI: `/report/{genome_id}` (always deterministic), `/report/{genome_id}/narrative` (LLM path + verifier gate + envelope `{ok, source: llm|template, data, error}`); `model_card.py` for reliability diagram + Brier + coverage manifest.
9. Streamlit UI: verdict table with NO-CALL styling, KNOWN_MECHANISM vs STATISTICAL_ASSOCIATION badges, model-card panel, non-dismissible disclaimer banner, collapsible AI-narrative labeled with `review_status`.
10. CI: `MockLLMClient`-scripted tests for generator (happy path) and verifier (grounded-pass + unsupported-claim-reject) + schema tests asserting disclaimer presence and that no LLM-writable field can carry a verdict/confidence; document the boundary rules as an ADR.

## Risks & to-validate

- LLM-as-reviewer shares a failure-mode ceiling with the generator (both foolable by the same fluent-but-wrong text) — mitigated but not eliminated by the deterministic substring/number pre-check.
- OpenAI `response_format=json_schema` is not a drop-in alias for Anthropic tool-forcing — `openai_backend.py` needs its own StopReason mapping + tool-call parsing (real port work).
- Under 24h pressure the most likely violation is skipping the deterministic builder and having the generator read AMRFinderPlus/ML output directly to "reason about" resistance in one LLM call — called out in CLAUDE.md/ADR as the boundary not to cross (fastest-looking, most damaging shortcut).
- A thin MVP KB pushes most `EvidenceItem`s to STATISTICAL_ASSOCIATION-only with no citation — acceptable, but stated as an explicit MVP limitation in the model card, not silently under-cited.
- If the OpenAI key/quota fails mid-demo, the deterministic no-LLM path must be rehearsed as a first-class demo path so a live failure doesn't look broken.

## Sources

Design result (reuse-grounded); grounds in the reuse assets listed in [`../reuse-inventory.md`](../reuse-inventory.md) and the research findings in this folder.
