# ADR-0023 — Reviewer per-drug number binding, published-string tripwire & disclaimer-dedup hardening

- **Date:** 2026-07-19
- **Status:** Accepted
- **Origin:** Agent-proposed / human-approved (issue #45, surfaced by the PR #42 adversarial verification). **Safety-critical (defense-in-depth).**

## Context

The PR #42 adversarial verification confirmed the report/narrative safety invariants hold — the lab-confirmation disclaimer can never be lost (golden rule #4) and the LLM can never fabricate a *verdict* (golden rule #1) — but surfaced three low-severity, defense-in-depth weaknesses in the deterministic pre-check (`report/reviewer.py`) and the pipeline's disclaimer-dedup (`report/pipeline.py`). None was a live clinical-safety hole (all are backstopped by the LLM judge and produce no human-legible misinformation), so they were tracked in #45 rather than blocking #42. This ADR records the hardening; it **refines the number-grounding clause of ADR-0020**.

The three issues (all in `report/`):
- **A — validated ≠ published.** The pre-check validated `_section_prose` (order: summary, caveats, narratives) while the pipeline published `_flatten` (order: summary, drug-prefixed narratives, filtered caveats, disclaimer) and never re-reviewed the flattened string. `_PERCENT_RE`'s `\s*` spanned a newline, so a bare digit ending a narrative + a `%`-leading caveat formed an `NN%` token that existed only in the published string (reproduced: precheck `findall`=`[]`, flatten `findall`=`['88']`).
- **B — global (not per-drug) number membership.** A confidence-shaped `N%` was accepted if it appeared *anywhere* in the report; a per-drug narrative could state `48%` where the `48` came from another drug's `OXA-48`.
- **C — loose disclaimer-dedup.** `_restates_disclaimer` fired on `"confirm" in lowered and ("laborator" or "susceptibility test")` — the substring `"confirm"` also matched `"confirmed"`, silently dropping a legitimate distinct caveat ("…the blaKPC allele could not be confirmed — laboratory re-testing advised").

## Decision

**Number grounding is per structured component (refines ADR-0020).** ADR-0020 said "a confidence-shaped `N%` must match one of the report's own numbers, not merely KB text." This ADR refines *the report's own numbers* to *the specific drug's own numbers* wherever attribution is exact:
- A per-antibiotic narrative's `N%` must equal **that drug's rendered confidence** (`report/narrative.render_row`, made public — the single source of truth for what each drug's canonical row prints, so the check can never drift from the renderer). A general number must be in that drug's own row **or a KB chunk cited FOR that drug** (`retrieval[drug]`), not merely somewhere in the report.
- The free-text `summary`/`caveats` are overview prose (not drug-bound), so they keep **global** membership: a percent must be one of the report's own numbers; any other number must appear in the report or a cited chunk. (Number-fabrication in free text stays the LLM judge's backstop — the same posture ADR-0020 already accepts for that surface.) **Follow-up (deferred out of #45's per-drug scope, PR #42 senior review):** binding free-text percents to the rendered-*confidence* set (not all report numbers) would close the same gene-digit→percent collision on the summary surface at low false-reject cost, making the "the deterministic layer alone cannot ship a fabricated confidence" property uniform across every prose surface. Tracked as a follow-up, not done here.

**`_PERCENT_RE` is intra-line only** (`[^\S\r\n]*%`, was `\s*%`): a `%` can no longer bind to a digit across a newline. With per-component validation this makes the reorder/parser-differential unreachable for numbers (`_NUMBER_RE` has no whitespace; verdict phrases contain a literal space a `\n` cannot satisfy; drug names are single tokens).

**A published-string tripwire fails closed.** `reviewer.published_percents_grounded(flattened, report)` asserts every percent in the *final published* string is one of the report's own numbers; `pipeline.narrate_report` gates publication on it and falls back to the deterministic template otherwise. It is provably redundant after a passing pre-check today, but converts the non-local "validated == published" proof into a locally-enforced, fail-closed invariant so a future refactor cannot silently reopen the differential.

**Disclaimer-dedup uses a word-boundary + canonical-skeleton match.** `_restates_disclaimer` drops a caveat only when it matches `\bconfirm\b` **and** `"result"` **and** (`"laborator"` OR `"susceptibility test"`) — the canonical disclaimer's distinctive "confirm every result with … laboratory … testing" skeleton. `\bconfirm\b` no longer fires on `"confirmed"`, and the `"result"` anchor spares a specific-finding hedge ("Confirm the porin call by phenotypic susceptibility testing"); the broad lab conjunct still de-duplicates a "laboratory testing" restatement, not only the exact "susceptibility testing".

Rejected: re-running the full pre-check on the flattened blob (loses the per-drug structure the binding needs); an overlap-threshold disclaimer match (fragile to plural/singular and word choice — a singular "result" vs "results" swings a Jaccard score); binding per-drug percents to *all* the drug's rendered numbers rather than only its confidence (would re-admit the `OXA-48`→`48%` collision).

## Consequences

- (+) The number guard's strength no longer depends on which prose surface a claim lands in — the cross-drug confidence collision (B) and the reorder differential (A) are closed deterministically, not only via the LLM judge.
- (+) The tripwire makes "what we validate == what we publish" a fail-closed, test-pinned invariant.
- (+) Disclaimer-dedup no longer discards real clinical hedging (C), consistent with the word-boundary matching already used in the reviewer.
- (−) **Stricter fail-close (accepted, safe direction):** a per-drug narrative that quotes a KB-only percent (e.g. "95% identity") or a number ungrounded for that drug (e.g. "3rd-generation" when "3" is not in that drug's row/chunks) is now rejected → deterministic template. This is the same richness-for-safety trade ADR-0020 already makes, extended to per-drug prose; the disclaimer and every verdict are unaffected.
- (−) A disclaimer restatement that omits the "result" skeleton is not de-duplicated → at worst a cosmetic double disclaimer, never a lost caveat or a lost mandatory disclaimer.
- Pinned by `tests/report/test_reviewer.py` (per-drug percent/number binding, intra-line regex, render_row percent-purity, panel-drug-in-prose), `tests/report/test_pipeline.py` (caveat preservation, restatement dedup, flatten differential, tripwire fail-close) and `tests/report/test_safety_invariants.py` (tripwire helper).
