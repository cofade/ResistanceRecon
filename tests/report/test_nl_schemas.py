"""Safety-invariant tests for the LLM I/O schemas (golden rule #1, structural).

No narrator/reviewer output schema may carry a field an LLM could use to state or change a
verdict/confidence/SIR class. Enforced by introspecting `model_fields`, so it survives prompt
drift and model upgrades.
"""

from __future__ import annotations

import pytest

from genome_firewall.report.nl_schemas import (
    ClaimCheck,
    NLDrugNarrative,
    NLReportSection,
    ReportVerdict,
)

_FORBIDDEN = {
    "verdict",
    "calibrated_confidence",
    "confidence",
    "sir",
    "sir_label",
    "probability_resistant",
    "conformal_set",
}


@pytest.mark.parametrize("model", [NLReportSection, NLDrugNarrative, ReportVerdict, ClaimCheck])
def test_llm_schema_carries_no_verdict_or_confidence_field(model: type) -> None:
    assert _FORBIDDEN.isdisjoint(model.model_fields)


@pytest.mark.parametrize("model", [NLReportSection, NLDrugNarrative, ReportVerdict, ClaimCheck])
def test_llm_schemas_forbid_extra_fields(model: type) -> None:
    assert model.model_config.get("extra") == "forbid"


def test_report_verdict_grounding_score_is_bounded() -> None:
    with pytest.raises(ValueError):
        ReportVerdict(grounding_score=1.5, overall_pass=True)
