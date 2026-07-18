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
