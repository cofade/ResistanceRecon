# ADR-0005 — Homology-aware grouped train/test split

- **Date:** 2026-07-18
- **Status:** Accepted
- **Origin:** Agent-proposed / human-approved.

## Context

K. pneumoniae has a clonal population structure (e.g. ST258/ST512). A random row-level split leaks near-identical genomes across train/test and inflates every metric — the classic weak-submission failure the challenge calls out. Multiple AST rows also share a `genome_id`.

## Decision

Group by **MLST sequence type** (from BV-BRC metadata) as the primary key; fall back to **Mash single-linkage clustering @ ANI 99.5%** (distance ~0.005; skani if time permits) for isolates missing an ST or to catch cross-ST near-duplicates. Split with `StratifiedGroupKFold` on the group id, plus an explicit **leave-one-group-out unseen-lineage holdout**. Report metrics marginally, per group, and on the unseen holdout.

## Consequences

- (+) Honest generalization estimates; directly demonstrates learning of resistance signal vs memorizing clones.
- (−) A dominant resistant clone can degrade `StratifiedGroupKFold` toward `GroupKFold`; per-fold class balance must be inspected/reported.
- **Highest-value correctness item** — explicit no-leakage test required. Detail: [research-findings/ml-methodology.md](../research-findings/ml-methodology.md).
