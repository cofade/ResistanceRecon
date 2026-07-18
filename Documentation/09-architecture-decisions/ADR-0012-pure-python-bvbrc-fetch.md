# ADR-0012 — Pure Python for the BV-BRC fetch, not WSL2/p3-CLI

- **Date:** 2026-07-18
- **Status:** Accepted
- **Origin:** Human, logged per the CLAUDE.md ADR trigger "choosing between non-trivial approaches".

## Context

Documentation/research-findings/bv-brc-data-access.md's download recipe is written as WSL2 bash
(the official `p3-*` Perl CLI + `wget`/`lftp`), mirroring the project's existing AMRFinderPlus/
Docker/WSL2 toolchain (golden rule #6). The actual mechanics it drives — an FTPS flat-file/`.fna`
download and a Solr HTTPS Data API — are both reachable from plain Python with no external tool.

## Decision

Implement `scripts/fetch_bvbrc_data.py` in pure Python: `ftplib.FTP_TLS` for the FTPS flat file and
per-genome `.fna`, stdlib `urllib.request` for the Solr Data API cross-check. No `p3-*` CLI, no WSL2
dependency for EPIC 1 (WSL2/Docker remains required for AMRFinderPlus itself, per ADR-0002 — this
ADR only concerns the data-*fetch* step).

## Consequences

- (+) Cross-platform (native Windows, no WSL2 required just to pull labels/FASTAs), unit-testable
  (the pure functions in `predictor/dataset.py` need no external tool to exercise), and matches the
  project's "demo pure-Python, no bio-tools in CI" constraint directly.
- (+) One fewer heavy toolchain to install/pin for a step that is fundamentally two HTTP-adjacent
  protocols (FTPS, HTTPS/Solr), not genome annotation.
- (−) FTPS passive-mode data transfers can be blocked by consumer-router FTP ALGs in a way the
  official `p3-*`/`wget` tooling might handle differently (or might not — untested); see
  Documentation/11-risks-and-technical-debt/README.md §11.4 for the concrete failure observed and
  its mitigation (actionable error hint, not a code workaround — this is a network-layer limit).
- **Alternative considered:** WSL2 + official `p3-*` CLI, as the research doc's recipe describes.
  Rejected as the *default* — it adds a second heavy toolchain purely to speak FTPS/HTTPS, which
  Python already does natively; kept as a documented fallback if pure-Python FTPS proves unreliable
  across enough environments to matter.
