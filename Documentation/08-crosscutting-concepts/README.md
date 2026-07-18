# 8. Crosscutting Concepts

## Golden rules (see CLAUDE.md)

1. **The LLM never predicts.** Verdicts/confidence come only from `predictor/` (LR + calibration + conformal). LLM output schemas contain no verdict field. CI import-boundary test forbids `predictor/`/`features/`/`reader/` importing `llm/`.
2. **Defensive by construction.** No sequence-writing capability exists.
3. **Ground Truth First.** Known mechanism (deterministic gene/mutation) is never conflated with a statistical association (model/SHAP). The `evidence_category` field carries this.
4. **Lab-confirmation disclaimer** enforced at three points (Pydantic validator, LLM-reviewer, UI banner).
5. **No raw dicts across boundaries** — Pydantic schemas everywhere.

## Calibration & no-call

Calibrated probabilities (sigmoid, `cv='prefit'` on a grouped calibration fold) + conformal prediction sets that map to work/fail/no-call. `{S,R}` = ambiguous no-call; `{}` = novel/OOD no-call. Default alpha 0.10 with a documented sensitivity table. Detail: [`research-findings/ml-methodology.md`](research-findings/ml-methodology.md).

## Honest generalization

Homology-aware grouped split (MLST ST primary; Mash single-linkage @ ANI 99.5% fallback), `StratifiedGroupKFold` + an explicit unseen-lineage holdout. Metrics reported marginally, per genetic group, and on the unseen holdout.

## Error handling & degradation

Every external tool/network call returns an `{ok, source, error}` envelope; the API surfaces failures as structured 503s. The deterministic (no-LLM, cache-backed) path is a first-class demo path so an OpenAI or Docker outage degrades gracefully.

## Reproducibility

Pinned AMRFinderPlus Docker tag + DB version recorded per run; versioned `feature_schema.json`; MLflow tracking; `ground-truth/decisions.jsonl` decision trail.

## Integration-test mandate

Every user story ships at least one end-to-end integration test through a realistic boundary (`@pytest.mark.integration`, driven by `MockAnnotator` — never Docker/AMRFinderPlus in CI). **No merge without it. No exceptions.** A feature is not mergeable with only happy-path unit tests when a boundary workflow is available. Bug fixes pin their regression at the appropriate layer. The seven shapes (detail + what counts as evidence in `.claude/skills/gf-validation-and-qa/`):

1. **Data pipeline** — fixture data → normalized labels → persisted dataset contract.
2. **Reader** — FASTA fixture → MockAnnotator → feature vector (matches `feature_schema.json`).
3. **Predictor** — feature vector → target gate / model / calibration / conformal → verdict.
4. **Report** — prediction → complete report with `evidence_category` + disclaimer.
5. **LLM** — frozen report → narrative/reviewer → accepted, or fail-closed deterministic template.
6. **API** — request → structured response / `{ok:false}` → 503 error envelope.
7. **UI** — upload/demo flow → rendered verdict / evidence / non-dismissible disclaimer.

## Evidence hierarchy

Weakest → sovereign: **green CI < full local quality gates < independent senior review < manual testing by the user**. Green CI means "the assertions someone wrote passed", not "correct"; never overclaim a lower tier as proof. Manual testing is the final, user-owned gate — a change stays in a draft PR until the user explicitly confirms it passed (ADR-0010). Each gate's specific limitations are documented in `gf-validation-and-qa`.
