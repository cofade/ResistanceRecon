"""Structured I/O schemas for the additive LLM narrative sub-pipeline.

Golden rule #1 is enforced *structurally* here: neither the narrator output (``NLReportSection``)
nor the reviewer output (``ReportVerdict``) carries a verdict / confidence / SIR field. There is
nothing for an LLM to populate that could become a prediction -- the narrative may only
*reference* values already present in the frozen ``GenomeReport``. These live in ``report/``,
not the frozen ``schemas.py``.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class _LLMSchema(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class NLDrugNarrative(_LLMSchema):
    """Prose for one antibiotic. ``narrative`` must reference only report/KB facts."""

    antibiotic: str
    narrative: str
    citations: tuple[str, ...] = ()


class NLReportSection(_LLMSchema):
    """The grounded natural-language narrator output. No numeric verdict/confidence field."""

    summary: str
    per_antibiotic: tuple[NLDrugNarrative, ...]
    caveats: tuple[str, ...] = ()


class ClaimCheck(_LLMSchema):
    """One grounding judgement about a claim in the narrative."""

    claim: str
    supported: bool
    evidence_ref: str | None = None


class ReportVerdict(_LLMSchema):
    """The reviewer's groundedness judgement. It judges *grounding*, never re-predicts:
    no verdict/confidence/SIR field exists here either."""

    grounding_score: float = Field(ge=0.0, le=1.0)
    per_claim: tuple[ClaimCheck, ...] = ()
    overall_pass: bool
