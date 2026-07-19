"""Orchestrates the additive LLM narrative: retrieve KB citations -> narrate -> review ->
fail-closed selection. Returns a NarrativeEnvelope (mirroring the {ok,source,error} pattern)
so the review outcome is machine-readable without mutating the frozen GenomeReport schema.

The deterministic template is the fallback-of-record: whenever the LLM is disabled, errors, or
its narrative is rejected, ``narrative_summary`` is the deterministic render and ``review_status``
records why. The disclaimer is present on every branch.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Literal

from pydantic import BaseModel, ConfigDict

from genome_firewall.kb.evidence_rag import EvidenceRAG
from genome_firewall.kb.retriever import RetrievedChunk
from genome_firewall.llm.client import LLMClient
from genome_firewall.llm.errors import LLMError
from genome_firewall.report.narrative import render_deterministic_narrative
from genome_firewall.report.narrator import generate_narrative
from genome_firewall.report.nl_schemas import NLReportSection, ReportVerdict
from genome_firewall.report.reviewer import review_narrative
from genome_firewall.schemas import GenomeReport

ReviewStatus = Literal["llm_output_accepted", "llm_output_rejected", "llm_disabled"]
NarrativeSource = Literal["llm", "template"]


class NarrativeEnvelope(BaseModel):
    """The narrative pipeline result: the report (with narrative_summary filled) + provenance."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    report: GenomeReport
    review_status: ReviewStatus
    source: NarrativeSource
    grounding: ReportVerdict | None = None
    error: str | None = None


def _with_summary(report: GenomeReport, summary: str) -> GenomeReport:
    return report.model_copy(update={"narrative_summary": summary})


def _template_envelope(
    report: GenomeReport,
    review_status: ReviewStatus,
    *,
    error: str | None = None,
    grounding: ReportVerdict | None = None,
) -> NarrativeEnvelope:
    report_with_summary = _with_summary(report, render_deterministic_narrative(report))
    return NarrativeEnvelope(
        report=report_with_summary,
        review_status=review_status,
        source="template",
        grounding=grounding,
        error=error,
    )


def _restates_disclaimer(caveat: str) -> bool:
    """True when an LLM caveat restates the lab-confirmation disclaimer (which the pipeline
    appends verbatim). Dropping it avoids the double disclaimer the model produces when it adds
    its own; the canonical disclaimer from ``report.disclaimer`` still stands (golden rule #4)."""
    lowered = caveat.lower()
    return "confirm" in lowered and ("laborator" in lowered or "susceptibility test" in lowered)


def _flatten(section: NLReportSection, report: GenomeReport) -> str:
    lines = [section.summary]
    lines.extend(f"{d.antibiotic}: {d.narrative}" for d in section.per_antibiotic)
    lines.extend(c for c in section.caveats if not _restates_disclaimer(c))
    lines.append(report.disclaimer)  # canonical disclaimer, exactly once (golden rule #4)
    return "\n".join(lines)


def _retrieve(
    report: GenomeReport, retriever: EvidenceRAG
) -> Mapping[str, Sequence[RetrievedChunk]]:
    return {
        p.antibiotic: retriever.retrieve_for_genes(p.supporting_features, p.antibiotic)
        for p in report.predictions
    }


def narrate_report(
    report: GenomeReport, *, client: LLMClient | None, retriever: EvidenceRAG | None = None
) -> NarrativeEnvelope:
    """Produce the narrative envelope for a frozen report, failing closed to the template."""
    if client is None:
        return _template_envelope(report, "llm_disabled")

    retrieval = _retrieve(report, retriever) if retriever is not None else {}

    try:
        section = generate_narrative(report, retrieval, client)
    except LLMError as exc:
        return _template_envelope(report, "llm_output_rejected", error=f"narrator failed: {exc}")

    outcome = review_narrative(section, report, retrieval, client)
    if not outcome.passed:
        return _template_envelope(
            report, "llm_output_rejected", error=outcome.reason, grounding=outcome.verdict
        )

    report_with_narrative = _with_summary(report, _flatten(section, report))
    return NarrativeEnvelope(
        report=report_with_narrative,
        review_status="llm_output_accepted",
        source="llm",
        grounding=outcome.verdict,
    )
