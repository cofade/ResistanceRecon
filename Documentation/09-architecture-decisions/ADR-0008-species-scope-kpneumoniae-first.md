# ADR-0008 — Klebsiella pneumoniae first; MRSA as documented follow-up

- **Date:** 2026-07-18
- **Status:** Accepted
- **Origin:** Human.

## Context

The challenge rewards doing ONE species and a few antibiotics well over broad-but-shallow coverage. Time is 24h, depth-first.

## Decision

Scope the MVP to *Klebsiella pneumoniae* (taxon 573) with a 5-antibiotic panel: meropenem, ceftriaxone, ciprofloxacin, gentamicin, trimethoprim-sulfamethoxazole. Ampicillin is handled as a fixed intrinsic-resistance flag (chromosomal SHV-1), excluded from the ML panel. Colistin is a documented stretch. *S. aureus* / MRSA is the next documented milestone, not started until K. pneumoniae is solid.

## Consequences

- (+) Rich lab-AST data, clear mechanisms, clean calibration story; foundations (schemas, pipeline, envelope) generalize to a second species.
- (−) Coverage explicitly limited; stated plainly in the model card and UI ("not covered").
- Detail: [research-findings/antibiotic-panel.md](../research-findings/antibiotic-panel.md).
