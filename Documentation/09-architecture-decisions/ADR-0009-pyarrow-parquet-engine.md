# ADR-0009 — Add pyarrow as the Parquet engine

- **Date:** 2026-07-18
- **Status:** Accepted
- **Origin:** Agent-proposed (EPIC 1 implementation), logged per the CLAUDE.md ADR trigger "adding a dependency".

## Context

The PRD's Artifacts section already commits to Parquet for every processed table
(`data/processed/{feature_matrix,labels}.parquet`, `models/.../feature_schema.json` siblings).
`pandas.DataFrame.to_parquet`/`read_parquet` require a Parquet engine to be installed;
pandas ships with neither `pyarrow` nor `fastparquet` as a hard dependency. EPIC 1
(`scripts/build_dataset.py`) is the first code to actually write `labels.parquet`, and EPIC 3's
`predictor/split.py`/`train.py` will be the first to read it back — so this is core, not optional,
infrastructure, not a per-script convenience import.

## Decision

Add `pyarrow>=16` to the core `dependencies` list in `pyproject.toml` (not an optional extra).
pyarrow over fastparquet: it's the pandas-recommended default engine, has first-class type
fidelity for nullable integer/string columns (relevant to `labels.parquet`'s nullable
`mic_value`/`mlst_st` columns), and is already a transitive dependency of several `ml`/`rag`
extras this project will need later (e.g. via `pandas`'s own ecosystem), so it does not add a
meaningfully new supply-chain surface.

## Consequences

- (+) `to_parquet`/`read_parquet` work out of the box for every module, not just `scripts/`.
- (+) Nullable dtypes round-trip correctly (important for `mlst_st`, `mic_value`, tie-dropped
  counts) — CSV would silently stringify/lose these.
- (−) One more compiled wheel in the dependency tree (larger install size than CSV-only).
- **Alternative considered:** CSV for `data/processed/`. Rejected — the PRD already names
  `.parquet` explicitly, and CSV loses dtype fidelity for nullable numeric columns.
