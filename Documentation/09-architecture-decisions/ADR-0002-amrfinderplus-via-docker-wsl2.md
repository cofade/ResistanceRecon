# ADR-0002 — AMRFinderPlus via pinned Docker image under WSL2

- **Date:** 2026-07-18
- **Status:** Accepted
- **Origin:** Agent-proposed / human-approved.

## Context

AMRFinderPlus (NCBI) is the challenge's recommended default annotator. It is Linux-native (needs BLAST+/HMMER + a database) and not a Python library. We are on Windows.

## Decision

Run AMRFinderPlus via the official `ncbi/amr` Docker image under WSL2, pinned to a specific tag (≥ 4.2.5; e.g. `ncbi/amr:4.2.7-2026-05-15.1`) so binary + DB versions are fixed and recorded per run. Invoke with `-n <contigs> -O Klebsiella_pneumoniae --plus --name <id>`. Isolate all invocations behind `annotation/` with an `{ok, source, error}` envelope; provide a `MockAnnotator` over committed fixture TSVs. **AMRFinderPlus is never a Python import and never runs in CI.**

## Consequences

- (+) Reproducible, curated point-mutation calling (gyrA/parC); DB pinning; CI-testable pipeline via the mock.
- (−) WSL2/Docker is a local-setup and live-demo SPOF (mitigate with a feature-vector cache).
- **To-validate:** mock vs real output-schema drift (periodic manual re-check); flag `PARTIAL_CONTIG_END` as QC. Detail: [research-findings/amrfinderplus-features.md](../research-findings/amrfinderplus-features.md).
