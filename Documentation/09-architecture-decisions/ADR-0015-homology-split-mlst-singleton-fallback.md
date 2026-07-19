# ADR-0015 — Homology-aware split realized: MLST-ST primary with a singleton fallback

- **Date:** 2026-07-19
- **Status:** Accepted
- **Origin:** Agent-proposed / human-approved (EPIC 3 planning session, issue #18). Addendum to ADR-0005.

## Context

ADR-0005 fixed the homology-aware grouped split: group by MLST sequence type, with a **Mash single-linkage @ ANI 99.5%** fallback for isolates missing an ST. Implementing EPIC 3 surfaced that neither Mash nor skani is installed, and — like AMRFinderPlus — an external ANI tool could never run in CI. The Mash fallback only matters for genomes that lack a usable MLST ST; if that fraction is small, a simpler leakage-safe fallback suffices for the MVP.

## Decision

Group by MLST ST as the primary key (`predictor/dataset.mlst_group_id` → `st:<scheme>:<st>`). For any genome without a usable ST, assign it its **own singleton group** (`singleton:<genome_id>`) rather than clustering it. Clustering is behind a pluggable `predictor/split.ClusterBackend` protocol; `MlstStBackend` is the only shipped backend, and `AniClusterBackend` is a documented `NotImplementedError` stub. Real Mash/skani ANI-99.5% single-linkage clustering is **deferred** (tracked as a follow-up issue).

## Consequences

- (+) **Leakage-safe with no external tool:** a singleton group appears on only one side of any split boundary, so a missing-ST genome can never leak. Keeps CI and every test Docker/tool-free.
- (+) The pluggable backend makes adopting Mash/skani later a drop-in, not a rewrite.
- (−) Missing-ST genomes as singletons cannot be merged with a genuine near-duplicate that also lacks an ST, so a rare cross-ST near-clone pair could sit in different folds. This is a loss of *grouping power*, **not a leak** (different groups still satisfy the disjointness guarantee); recorded via `per_fold_class_balance`. Acceptable for the MVP; the deferred ANI backend closes it.
- Pinned by `tests/predictor/test_split.py` (no-leakage, min-n, degradation) and the `MlstStBackend`/singleton tests.
