# ADR-0009 — Versioning & release control (single-source; release automation deferred)

- **Date:** 2026-07-18
- **Status:** Accepted
- **Origin:** Agent-proposed / human-approved (issue #35 process transfer).

## Context

The scaffold duplicated the version in two places — `pyproject.toml` (`version = "0.1.0"`) and `src/genome_firewall/__init__.py` (`__version__ = "0.1.0"`) — kept in sync by hand. The reference project shows this is a real bug class: after a merge, stale reads of the "current version" produced wrong release tags. There is no `release.yml` in this repo yet, and at EPIC-0 (no shippable artifact) there is nothing to release.

## Decision

1. **Single source of truth:** `src/genome_firewall/__init__.py:__version__`. `pyproject.toml` declares `dynamic = ["version"]` and reads it via `[tool.hatch.version] path = "src/genome_firewall/__init__.py"`. The static `version` field is removed. There must never be a second place a version is written.
2. **Never create git tags manually.** When release automation is added, CI will be the only thing that creates tags.
3. **Release automation is deferred, not forgotten.** The intended future workflow: trigger on push to `main`; compute the next version from the latest tag plus the merged PR's semver label (`major`/`minor`, default **patch**); guard against re-running on the same tag; be idempotent. A `chore:`-style skip for version/doc-sync commits will be added with it.
4. **Observe release/CI state by transition, never by date.** Capture the top tag before merging and poll until it changes; a date match cannot detect a failed release.

## Alternatives considered

- **Keep the two-file manual sync** (reference-project status quo) — rejected: it preserves the drift-bug class for no benefit now that hatch can single-source.
- **Add a working `release.yml` immediately** — deferred: premature at EPIC-0; Genome Firewall ships as a library/API/UI (no OS installer), so the release shape differs from the reference and is better designed when there is something to release.

## Consequences

- (+) The drift-bug class is designed out; `uv build` derives the version from one place.
- (+) The interim rules (no manual tags, single source, state-transition observation) are documented before EPIC 1 accelerates.
- (−) No automated releases yet; this ADR must be revisited (as an addendum) when `release.yml` is added.
- Files: `pyproject.toml`, `src/genome_firewall/__init__.py`. Cross-refs: `CLAUDE.md` "Versioning & release", `gf-change-control` §4.
