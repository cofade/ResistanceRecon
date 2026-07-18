# 11. Risks and Technical Debt

## Top risks (with mitigations)

| Risk | Mitigation |
|---|---|
| **Homology-split bug leaks clonal genomes** → inflated metrics (highest-value to get right) | Group by clonal lineage (MLST + Mash), explicit no-leakage test, report per-fold class balance |
| **BV-BRC access/filename/`evidence` vocabulary uncertainty** | Verify FTPS + filename from a real client; enumerate all distinct `evidence` values before finalizing the filter |
| **Thin per-drug label volume after grouping** | Min-n gate (≥20 R / ≥20 S) → "insufficient data" no-call rather than an unstable model |
| **AMRFinderPlus 4.2.4 `--organism` DB bug; `PARTIAL_CONTIG_END` artifacts** | Pin tag ≥ 4.2.5; flag `PARTIAL_CONTIG_END` as QC, not a real partial gene |
| **No K. pneumoniae AMRFinderPlus concordance study found** | Run our own genotype→phenotype concordance check; treat as to-validate |
| **Mock/real annotator drift** (AMRFinderPlus never in CI) | Documented periodic manual re-validation against a real WSL2/Docker run |
| **LLM-boundary shortcut under time pressure** | CI import-boundary test + CLAUDE.md golden rule |
| **Demo SPOF: Docker/WSL2/OpenAI** | Pre-computed feature cache for demo genomes; deterministic no-LLM demo path; envelope degradation |

## Known technical debt (accepted for the 24h MVP)

- Single outer grouped split instead of full nested CV (documented; variance estimates are a follow-on).
- arc42-lite (deployment-view and quality-scenario chapters dropped).
- MRSA/second species deferred.
- Thin MVP AMR-mechanism KB → many evidence items are statistical-association-only (stated in the model card).
- `ml` optional-extra needs a `numba>=0.60` floor so the resolver skips the ancient `numba 0.53.1` / `llvmlite 0.36.0` (Python <3.10 only). Revisit when `shap` tightens its own floors.

## 11.4 Hard-won lessons from implementation

**This is the canonical, growing log of implementation lessons — the durable home the `debug-verbose` case studies and the `CLAUDE.md` "Known AI pitfalls" quick-list both point to.** Capturing a lesson here is **mandatory and non-negotiable**: every non-obvious bug and every hard-won lesson is recorded **in the same session it is learned** — no exceptions — as (1) an entry here, (2) a `debug-verbose` case study if it was instrumented, (3) a `CLAUDE.md` Known-AI-pitfall line, and (4) a pinning regression test. The senior-reviewer treats a missing capture as a P1. A lesson that lives only in chat is a lesson lost.

**House style (per entry):** a bold one-line imperative rule → the issue/PR that surfaced it → symptoms as observed → root cause with `file:function` references → the fix → the pinning test (`Pinned by tests/...`) → a generalized lesson.

Seed entries below are **standing traps** (design-time invariants, no incident yet); real incidents are appended in the same format as they occur.

- **Never give an LLM schema a verdict/confidence field.** _Standing trap._ Symptom: an LLM narrative could state a verdict the deterministic model never produced. Root cause: write access to a verdict field on an LLM output schema. Prevention/fix: LLM output schemas carry no verdict/confidence/SIR field; `scripts/check_import_boundary.py` + schema tests enforce it. Lesson: keep the LLM structurally unable to influence a verdict, not merely instructed not to.
- **Never split near-identical clonal genomes across train/test.** _Standing trap._ Symptom: inflated held-out accuracy. Root cause: a plain random split leaks near-duplicate clonal genomes across folds. Prevention/fix: homology-aware grouped split (MLST primary, Mash @ ANI 99.5% fallback) + an explicit no-leakage test. Lesson: correctness of the *split* dominates model choice for honest metrics.
