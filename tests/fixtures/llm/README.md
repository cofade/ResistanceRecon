# LLM response fixtures

Canned structured-output responses for driving `MockLLMClient` in CI. **Hand-authored** — no
live API was called (mirrors `tests/fixtures/amrfinder/README.md`). Each file is the exact JSON
shape `genome_firewall.llm.client.parse_structured_response` validates against the corresponding
schema, so mock and real backends are exercised through the same parser.

| File | Schema | Scenario it covers |
|---|---|---|
| `narrator_grounded.json` | `NLReportSection` | A grounded narrative referencing only report facts (meropenem LIKELY TO FAIL, ceftriaxone LIKELY TO WORK); passes the deterministic pre-check. Deliberately number-free so it is grounded against any confidence value. |
| `narrator_fabricated_number.json` | `NLReportSection` | A narrative with an invented confidence ("73%") not present in the report — the deterministic pre-check must reject it before any judge call, forcing the template fallback. |
| `reviewer_pass.json` | `ReportVerdict` | The LLM judge accepts (`overall_pass=true`). |
| `reviewer_fail.json` | `ReportVerdict` | The LLM judge rejects (`overall_pass=false`) — fail-closed to the template. |

None of these schemas carry a verdict/confidence/SIR field (golden rule #1) — asserted in
`tests/report/test_nl_schemas.py`.

## Re-validation

When the narrator/reviewer prompts or the OpenAI model change, re-capture a real response once
against the live backend and diff its shape against these fixtures (the model/prompt version the
fixtures target should be noted in the commit that updates them).
