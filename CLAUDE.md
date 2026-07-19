# Genome Firewall — Claude Code Instructions

Genome Firewall turns a reconstructed *Klebsiella pneumoniae* genome (FASTA) into a per-antibiotic verdict — **LIKELY TO WORK / LIKELY TO FAIL / NO-CALL** — with calibrated confidence and supporting evidence. Strictly **defensive** decision support; every result must be confirmed by standard lab testing.

> Full plan: [`prd.md`](prd.md). Research ground-truth: [`Documentation/research-findings/`](Documentation/research-findings/). This project is also a live case study of the six-layer Sustainable Agentic SE framework.

## Quick reference

Requires [uv](https://docs.astral.sh/uv/getting-started/installation/) on PATH (see README's Quickstart for the install command and a PATH troubleshooting note).

```bash
uv sync --all-extras                              # install (dev + optional groups)
uv run pytest                                     # tests (cov >= 80)
uv run ruff check src/ tests/ && uv run ruff format src/ tests/   # lint + format
uv run mypy src/                                  # type check (strict)
uv run bandit -r src/ scripts/ --severity-level high   # security scan
uv run uvicorn genome_firewall.api.main:app --reload   # API
uv run streamlit run src/genome_firewall/ui/app.py     # demo UI
```

## Documentation map

| Need | Location |
|---|---|
| Product vision / PRD | `Documentation/01-introduction-and-goals/prd.md` |
| Verbatim challenge brief | `Documentation/01-introduction-and-goals/challenge-brief.md` |
| arc42 chapters (12) | `Documentation/NN-*/README.md` (index: `Documentation/README.md`) |
| Research & design ground-truth | `Documentation/research-findings/` |
| Architecture Decision Records | `Documentation/09-architecture-decisions/` |
| Crosscutting concepts (golden rules) | `Documentation/08-crosscutting-concepts/README.md` |
| Model card / dataset datasheet | `Documentation/MODEL_CARD.md`, `Documentation/DATASHEET.md` (EPIC 7) |
| Roadmap | `Documentation/roadmap.md` |
| Decision log (paper ground-truth) | `ground-truth/decisions.jsonl` |
| Reuse inventory (local only) | `Documentation/reuse-inventory.md` (gitignored) |

## Golden rules (non-negotiable)

1. **The LLM never predicts.** The deterministic per-antibiotic logistic-regression + calibration + conformal pipeline in `predictor/` is the SOLE source of every work/fail/no-call verdict and confidence. LLM output is never a model input. `predictor/`, `features/`, and `reader/` must not import from `llm/` (enforced by a CI import-boundary test).
2. **Defensive by construction.** This system analyzes genomes; it never designs, modifies, synthesizes, or optimizes an organism. No sequence-writing capability may be added.
3. **Ground Truth First.** Never a claim without traceable evidence. Separate a KNOWN mechanism (deterministic gene/mutation hit) from a STATISTICAL association (model/SHAP signal) — the `evidence_category` field, and honest UI wording, enforce this.
4. **Every report carries the lab-confirmation disclaimer**, enforced at three points (Pydantic validator, LLM-reviewer check, non-dismissible UI banner).
5. **No raw dicts across module boundaries.** Use the Pydantic schemas in `schemas.py`; validate all external input at the boundary.
6. **AMRFinderPlus runs only via Docker/WSL2**, isolated behind `annotation/` with an `{ok, source, error}` envelope; it is never a Python import and never runs in CI (tests use `MockAnnotator` + committed fixture TSVs).

## Plan Mode (before any non-trivial change)

Non-trivial = anything beyond a typo or a one-line mechanical fix. Do not open an editor before these seven steps are done. This exists to stop technically-correct-but-architecturally-excessive or unsafe agent-generated designs — the smallest safe design wins.

1. **Enter Plan Mode.**
2. **Read the source of truth:** the GitHub issue + epic acceptance criteria, the `Documentation/roadmap.md` entry, the relevant ADRs, and the arc42 chapter(s) the change touches. Do not code from the title alone.
3. **Analyze the existing code and constraints** — what is already there, which golden rules and hidden contracts apply.
4. **Propose the smallest viable design.**
5. **Surface at least one alternative design and the failure modes** of each. State why the chosen one wins.
6. **Agree on the approach with the user.**
7. **Only then implement.**

Load `gf-change-control` at the start of any change; it carries the full checklist and the rationale behind every gate.

## Workflow (change lifecycle)

Every code, documentation, CI, or refactor change follows this. A feature branch is mandatory for all of them — never commit directly to `main`.

| Step | Action | Gate |
|---|---|---|
| 1 | Plan Mode (above); agree the approach | — |
| 2 | Feature branch: `git checkout -b feat/<epic>-<slug>` | Never on `main` |
| 3 | Implement with type hints; write the **end-to-end integration test** (see quality requirements — every user story ships one; no merge without it) | — |
| 4 | Run all quality gates locally until green | pytest cov ≥ 80, ruff, mypy strict, bandit, import-boundary |
| 5 | **senior-reviewer pass** on a fresh worktree/diff vs `main`; fix every P0/P1; **re-run until no P0/P1 remain** | Clean review is a hard gate |
| 6 | Update docs per the change-type matrix; append `ground-truth/decisions.jsonl` in the same session; write/update ADR if triggered | Docs before PR |
| 7 | Conventional commit `feat(<scope>): ...`; push; **open a DRAFT PR** with the manual-testing checklist filled in | Draft PR is the normal end state — never stop at "branch pushed", never open a non-draft PR |
| 8 | Wait for **CI green** (state transition, `gh pr checks <PR#> --watch --fail-fast`); never merge on red | — |
| 9 | **STOP.** The user performs manual testing. The PR stays draft until they explicitly confirm it passed | Manual testing is sovereign (below) |
| 10 | Only on the user's explicit confirmation: mark ready and merge. Then `/clear`; on abandonment, `/clear` too | Explicit user confirmation before ready/merge |

Automated tests and senior review are necessary but **never sufficient** — manual testing is the final, user-owned gate. Use `/finalize-epic` for the mechanical steps 6–10.

**The manual-testing checklist contains ONLY what you cannot run yourself.** Anything you can execute — loading an artifact, running the pipeline on local/fixture data, exercising an error path, inspecting committed metrics, running an opt-in or live test suite (`GF_RUN_LIVE=1`) — you MUST run and report as part of your own verification; never hand a runnable command to the user as if it were their task. Litmus test: if you ran a check to obtain its "expected output", it does not belong on the checklist. Reserve the checklist for genuinely human-owned judgment: visual/UX assessment, behaviour on the user's own hardware/infra, subjective quality or scientific-acceptability calls, and steps needing credentials or an environment you lack.

**Deferral safety.** When a plan defers scope out of the issue being worked (e.g. "build X" narrows to "build the input Y that X needs"), post a carry-forward comment on both the source issue and the issue that inherits the deferred work *before* starting implementation — so nothing is silently dropped. State what was deferred, why, and which issue now owns it.

## Evidence hierarchy (weakest → sovereign)

Never overclaim a lower tier as proof. Green CI does not mean "correct"; it means "the assertions someone thought to write passed."

1. **Green CI** — the assertions ran on a clean machine. Weakest; pins only what tests cover.
2. **Full local quality gates** — pytest cov ≥ 80 + ruff + mypy strict + bandit + import-boundary, all green locally.
3. **Independent senior review** — the `senior-reviewer` agent, fresh eyes, P0/P1 resolved, re-reviewed after fixes.
4. **Manual testing by the user** — **sovereign.** It has overturned reviewed-and-green work before and can drop a feature outright. Nothing merges without it.

## Quality gates (mandatory before every PR)

1. Local gates green: `pytest` (cov ≥ 80), `ruff check`, `ruff format --check`, `mypy --strict`, `bandit -r src/ scripts/ --severity-level high`, and `python scripts/check_import_boundary.py`.
2. The **senior-reviewer** agent (`.claude/agents/senior-reviewer.md`) runs against a fresh worktree/diff vs `main` and returns "mergeable as-is" or "mergeable with [minor changes]".
3. If it raises P0/P1s: fix, **re-run the agent, loop until no P0/P1 remain** (a review of the original is not a review of the fix).
4. Open the DRAFT PR only after 1 and 2 pass. Use `/finalize-epic` for the wrap-up. Coverage drops in `predictor/` or `reader/` (the trust-critical path) require an ADR.

## Skill library (routing map)

The authoritative trigger for each skill is its frontmatter `description`, not this table — but use the table to know what exists and which to load.

| Skill | Load it when |
|---|---|
| `gf-change-control` | Starting ANY change; branching, committing, opening/marking/merging a PR, versioning, or "is this action allowed?" |
| `gf-validation-and-qa` | Deciding what evidence a change needs; test authoring, completion criteria, PR readiness, evidence sufficiency |
| `gf-docs-and-writing` | Finishing any change (docs are owed); writing an ADR, risk entry, roadmap update; "where does this knowledge live?" |
| `gf-architecture-contract` | Designing a feature; "is this allowed?" for the LLM boundary, schemas, disclaimer, no-call semantics, annotation envelope |
| `gf-research-methodology` | Sourcing/validating a bio or ML claim; BV-BRC provenance; writing a `research-findings/` doc; KNOWN vs STATISTICAL |
| `gf-proof-and-analysis` | Justifying a threshold, statistical method, or a third-party tool's behavior (alpha, min-n, ANI, AMRFinderPlus output) — prove before adopting |
| `gf-failure-archaeology` | Before changing an existing subsystem; a quirk may be an intentional scar. Where past incidents/decisions live |
| `gf-pr-analysis` | Reviewing someone else's PR (not authoring); run every local gate + emit a manual-test plan |
| `finalize-epic` | The wrap-up sequence after review is clean (commit → push → draft PR → wait → user confirm → merge) |
| `debug-verbose` | First sign of any non-obvious bug — instrument and observe before theorising |
| `gf-build-and-run` | Installing, testing, or running the API/UI/CLI locally |
| `gf-data-and-annotation` | Sourcing BV-BRC data or running AMRFinderPlus (offline/dev only — never in CI) |

## Documentation-update matrix

Canonical version and house style live in `gf-docs-and-writing`; this compact copy is the quick reference. Before merge, verify the relevant docs are updated and cross-references are not stale.

| Change | Required documentation |
|---|---|
| New module or package | `Documentation/05-building-block-view/` + the architecture map |
| Runtime/pipeline behavior | `Documentation/06-runtime-view/` (sequence diagrams) |
| New data source or preprocessing rule | ADR + `research-findings/` + risks + dataset datasheet (when it exists) |
| Model/split/calibration/conformal change | ADR + `10-quality-requirements/` + risks + model card + `ground-truth/decisions.jsonl` |
| New API/UI capability | runtime/deployment docs + acceptance criteria + manual test plan |
| New domain term | `Documentation/12-glossary/` |
| New security or safety issue | risks/technical debt + a test + ADR if architectural |
| Non-obvious bug / hard-won lesson | §11.4 log (canonical) + Known AI Pitfalls (below) + `debug-verbose` case study + regression test — same session, no exceptions |
| Research/design finding | `Documentation/research-findings/` in the same session |

## Versioning & release

Release automation is **deferred** (there is no `release.yml` yet). Interim rules — full detail in `gf-change-control` and [ADR-0009](Documentation/09-architecture-decisions/ADR-0009-versioning-and-release-control.md):

- **Single source of truth:** `src/genome_firewall/__init__.py:__version__`. `pyproject.toml` reads it dynamically (hatch) — do not add a second static version.
- **Never create git tags manually.** When release automation lands, CI will own tags/versions (push to `main`, PR-label semver bump).
- Observe CI/release state by **transition**, never by grepping dates.

## Progress tracking

**Current phase:** EPIC 6 — Demo surface (Module 03b): `service.py` in-process orchestrator (`analyze_genome`, ADR-0022) that both the FastAPI backend (`api/`) and the Streamlit UI (`ui/`) call. All local gates green (372 passed, cov 96.9%); `main` (PR #42, EPIC 4+5) merged into the branch; draft PR pending user manual test. Prior phase: EPIC 3 — Predictor (Module 02). PR-B (predict/registry/tracking, issues #21/#22) implemented on branch `feat/epic3-predict-registry`: `predictor/{conformal,predict,errors,model_registry,experiment_tracking}`, `scripts/train_predictor.py`, ADR-0014, full PR-B test suite (conformal/registry/predict/tracking + PR-B e2e). All local gates green (219 passed, cov 96%). **Real training run done** on a 130-genome/67-ST BV-BRC subset (Docker AMRFinderPlus → feature matrix → train_predictor → 5/5 drugs trained, MLflow-tracked); real metrics in `models/results_summary.json` + per-drug `model_card.md` (honest: gentamicin AUROC 0.875 / PR-AUC 0.76; beta-lactam gate-negative residual thin at n=130, `conformal_guarantee_available=false` for 4/5 — surfaced, not hidden).
**Completed:** EPIC 0 scaffolding; EPIC 1 (PR #37); EPIC 2 (PR #38); EPIC 3 PR-A (split/gate/LR+calibration + features/ + HTTPS fetch + batch feature-matrix builder, ADRs 0015–0018; draft PR pending manual test) and PR-B (conformal + predict + typed-compat registry + MLflow tracking + train orchestration + real run, ADR-0014). EPIC 4+5 (report/llm/kb, ADRs 0019–0021) merged as PR #42. EPIC 6 (api/ui/service, ADR-0022) implemented this session — draft PR pending user manual test.
**Next up:** senior review → draft PR-B → user manual test → merge (PR-A then PR-B).
**Parallel package (Module 03a):** EPIC 4 + EPIC 5 implemented on `feat/epic4-5-report-and-llm` (forked off `main`, schema-decoupled from the EPIC 3 predict-registry session): `report/{inputs,evidence,builder,narrative,nl_schemas,narrator,reviewer,pipeline}.py`, `llm/` (client + MockLLMClient + OpenAI backend), `kb/` (BM25+embedding+RRF evidence RAG, offline-safe). ADRs 0019–0020. All local gates green (296 passed, cov 97.1%). Draft PR pending manual test; real OpenAI path is mock-only in CI.

Update this section at the start of each work session; do not reconstruct it from git history.

## Debugging protocol

Instrument with `print()` prefixed `[DEBUG]`; remove ALL before committing. Permanent logging uses `import logging`, never `print`.

## Known AI pitfalls (append as discovered)

**Capturing a lesson is mandatory — no exceptions.** Every non-obvious bug and every hard-won lesson is recorded **in the same session it is learned**: here (quick-list), in the canonical detailed log `Documentation/11-risks-and-technical-debt/README.md` §11.4, as a `debug-verbose` case study if instrumented, and pinned by a regression test. The senior-reviewer treats a missing capture as a P1. A lesson that lives only in chat is a lesson lost.

Format: symptom → root cause → prevention.
- **Symptom:** an LLM narrative states a verdict the model didn't produce. **Root cause:** LLM given write access to a verdict field. **Prevention:** LLM output schemas contain no verdict/confidence field; reviewer + schema tests enforce it.
- **Symptom:** inflated held-out accuracy. **Root cause:** near-identical genomes split across train/test. **Prevention:** homology-aware grouped split (MLST + Mash fallback); explicit no-leakage test.
- **Symptom:** FTPS control-channel handshake (connect/login/PROT P/PASV) succeeds but every data transfer (`LIST`/`RETR`) fails with `425 Unable to build data connection`. **Root cause:** a consumer-grade router's FTP ALG can't track FTPS's TLS-encrypted control channel and mishandles the passive-mode data connection — a network constraint, not a code defect. **Prevention:** a dedicated error hint (VPN / disable router FTP-ALG / different network) instead of a generic message; `@pytest.mark.live` tests catch this class of failure that fixture-only tests never can. See Documentation/11-risks-and-technical-debt/README.md §11.4.
- **Symptom:** a schema built from a pre-implementation research doc's paraphrase would reject 100% of real tool output. **Root cause:** AMRFinderPlus's actual `Method` values are X/P/N-suffixed (`ALLELEX`, `POINTX`, ...) and its columns are `Type`/`Subtype` (not "Element type"/"Element subtype"); the research doc's summary table used bare names that never appear in real output. **Prevention:** run the real tool at least once before finalizing a schema derived from documentation-paraphrase; caught before merge by a live Docker validation run during EPIC 2 implementation. See Documentation/11-risks-and-technical-debt/README.md §11.4.
- **Symptom:** BV-BRC Solr query returns `HTTP 400` for `eq(evidence,Laboratory Method)`; a `json(nl,map)` facet request returns a dict and breaks code written for Solr's default flat list. **Root cause:** un-encoded space in an RQL literal; a wrongly-assumed facet response shape. **Prevention:** encode RQL literals (`_rql_value`); a live test against the real API (`numFound=85291`, matching the research doc exactly). See Documentation/11-risks-and-technical-debt/README.md §11.4.
- **Symptom:** a `genome_sequence` HTTPS Data API query silently returns only the first 25 contigs (page cap 25,000), truncating a multi-contig assembly's FASTA with a `200 OK` and no error. **Root cause:** the BV-BRC Data API paginates and defaults to 25 rows; a partial FASTA is indistinguishable from a complete one without an external check. **Prevention:** request an explicit high `limit(...)` and validate the download's contig count/total length against the `genome` record (`fasta_sanity_problem`), rejecting on mismatch or on hitting the ceiling. See §11.4 and ADR-0016.
- **Symptom:** sklearn emits a `FutureWarning` that `penalty='l2'` is deprecated, and `CalibratedClassifierCV(cv='prefit')` no longer exists (sklearn ≥1.9). **Root cause:** scikit-learn 1.8 deprecated explicit `penalty=` on `LogisticRegression` and replaced `cv='prefit'` with `sklearn.frozen.FrozenEstimator`; the ADR-0003/0004 recipes predate that API. **Prevention:** rely on `LogisticRegression`'s default (L2) instead of passing `penalty='l2'`; wrap the prefit model in `FrozenEstimator` for calibration. Same method, adapted API — recorded so ADR text and code don't silently diverge. See §11.4.
- **Symptom:** the LLM-narrative reviewer's deterministic pre-check leaked a wrong per-drug verdict into the clinician-facing narrative four review rounds running — each time in a different prose surface (global test → per-antibiotic entry → summary → proximity plural → foreign drug inside an entry). **Root cause:** every round hardened one *instance* while leaving the unstated invariant "this prose is about exactly its own drug(s)" soft in the next field; membership/proximity are heuristics, not guarantees. **Prevention:** enforce the *shape* as a structural contract across all symmetric fields at once — a per-antibiotic narrative names no other panel drug; the free-text summary/caveats state no verdict/causal phrase at all — and add a regression test per field. Hardening field A while leaving the assumption in field B ships the same bug again. See §11.4.
- **Symptom:** the homology-aware grouped split silently degraded to a random per-genome split on live data (every genome its own singleton group), defeating ADR-0005. **Root cause:** BV-BRC's HTTPS `genome.mlst` field is `MLST.klebsiella.258` (a leading `MLST.` tag the EPIC 1 fixtures lacked); `parse_mlst`'s `^([A-Za-z0-9_]+)\.(\d+)$` matched nothing and returned `(None, None)` for all 39,628 genomes. **Prevention:** strip the `MLST.` prefix before matching (36,885/39,628 recover a real ST; the 120-genome subset then spans 67 STs, not 120 singletons); smoke-check every parser against the live API, not only fixtures — same class as the AMRFinderPlus Method-suffix and genome_sequence page-cap lessons. See §11.4.
- **Symptom:** a `likely_to_work` verdict falsely annotated "no known resistance determinants detected" for a genome that carries one. **Root cause:** the per-genome evidence path reused the model card's top-20 coefficient DISPLAY slice as its attribution source, zeroing every present feature ranked #21+. **Prevention:** persist the FULL signed coefficient vector for attribution and slice only for display — never let a display/summary artifact double as a computation input; pinned by a >20-feature regression test. See §11.4.
- **Symptom:** the opt-in FTPS live test failed with a clean `550 ... PATRIC_genome_AMR.txt: No such file or directory` — control channel fine, file just gone. **Root cause:** BV-BRC renamed its AMR flat file server-side, singular `PATRIC_genome_AMR.txt` → plural `PATRIC_genomes_AMR.txt`; the fetch code pinned one name even though the ambiguity was already documented. **Prevention:** `KNOWN_FLATFILE_NAMES` + `ftps_download_flatfile()` try every known name on a `550` and stop on any other error (a `425`/timeout is not a naming problem); a hardcoded upstream filename is a live dependency, not a constant. See §11.4 (issue #41).
- **Symptom:** a `fastapi.testclient.TestClient` (or Streamlit `AppTest`) test hangs forever on Windows (killed at timeout, no output) under the autouse `_no_network` guard. **Root cause:** TestClient/AppTest spin up an asyncio event loop whose self-pipe calls `socket.socketpair()`; on Windows the pure-Python fallback routes through the monkeypatched `socket.socket`, the guard's `RuntimeError` kills the anyio portal thread, and the caller blocks forever. On Linux/CI `socketpair` uses the native C call and bypasses the patch, so CI is unaffected — a Windows-only local hang. **Prevention:** `tests/_netguard.py` autouse fixture (re-exported into `tests/api/conftest.py` + `tests/ui/conftest.py`) restores the real `socket.socket` for these deliberately-offline in-process-ASGI suites. See §11.4 (EPIC 6).
- **Symptom:** `POST /predict` with a malformed FASTA returns a generic 503 instead of 422; a `PermissionError [WinError 32]` masks the real `FastaParseError`. **Root cause:** `SeqIO.parse(Path)` leaves the file handle open when a parse FAILS mid-iteration, and on Windows the open handle blocks the upload's `TemporaryDirectory` cleanup, whose exception supersedes the in-flight `FastaParseError`. **Prevention:** `service.analyze_genome` validates from an in-memory `io.StringIO` (which holds no OS handle), never the on-disk path, so the temp file cleans up regardless of parse outcome. See §11.4 (EPIC 6).
- **Symptom:** an untrained (below-min-n) drug carrying a called known resistance mechanism renders `no_call/no_signal` in the served report while the sovereign predictor forces `likely_to_fail/known_mechanism`. **Root cause:** two frozen derivations of the verdict apply the same guards in a different ORDER — `predict.py` checks the gate before the missing-model case, but `report.builder` checks `insufficient_data` before `gate.fired`, and the orchestrator's adapter set `insufficient_data` without consulting the gate. **Prevention:** the adapter evaluates the gate and sets `insufficient_data = not gate_fired`; the reconciliation test exercises the untrained-gate-firing and model-driven-fail EDGE branches, not just the all-trained happy path. See §11.4 (EPIC 6).

## ADR triggers

Write an ADR in `Documentation/09-architecture-decisions/` when: adding a dependency; a new bio data source; changing calibration/conformal/split method; any change to the LLM boundary; choosing between non-trivial approaches. Format: title, date, status, context, decision, consequences.
