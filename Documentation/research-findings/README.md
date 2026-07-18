# Research & Design Findings

Web-grounded research and reuse-grounded design produced during the planning phase (2026-07-18) by a 7-agent design workflow. These documents are the **ground truth** the implementation is built from — each empirical claim traces to a cited source or a named reuse asset.

## Research (web-grounded)

| Doc | Topic |
|---|---|
| [`bv-brc-data-access.md`](bv-brc-data-access.md) | How to self-source K. pneumoniae genomes + laboratory AST labels from BV-BRC; the `evidence == 'Laboratory Method'` filter; download recipe |
| [`amrfinderplus-features.md`](amrfinderplus-features.md) | AMRFinderPlus via pinned Docker/WSL2; output schema; gene/mutation feature-matrix construction; the molecular-target gate |
| [`ml-methodology.md`](ml-methodology.md) | Per-antibiotic logistic regression, sigmoid calibration, conformal no-call, homology-aware grouped split, metrics |
| [`antibiotic-panel.md`](antibiotic-panel.md) | The 5-drug panel with per-drug resistance-gene → molecular-target mappings and no-call justifications |

## Design (reuse-grounded)

| Doc | Topic |
|---|---|
| [`architecture.md`](architecture.md) | `genome_firewall` package layout, Pydantic schema set, deterministic/model boundary, FastAPI+Streamlit surface, artifact layout |
| [`se-scaffolding.md`](se-scaffolding.md) | Six-layer Sustainable Agentic SE scaffolding: files to create, ADRs to seed, CI constraints |
| [`llm-boundary.md`](llm-boundary.md) | Where LLMs are used vs deterministic; structural prediction-path exclusion; responsibility-requirement mapping |

> Source of truth: workflow journal `wf_8772eb55-01b/journal.jsonl`. Where a finding is marked *to-validate*, it must be confirmed against a live tool/dataset before being relied upon.
