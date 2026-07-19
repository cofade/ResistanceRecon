"""Orchestrates the additive LLM narrative: retrieve KB citations -> narrate -> review ->
fail-closed selection. Returns a NarrativeEnvelope (mirroring the {ok,source,error} pattern)
so the review outcome is machine-readable without mutating the frozen GenomeReport schema.

The deterministic template is the fallback-of-record: whenever the LLM is disabled, errors, or
its narrative is rejected, ``narrative_summary`` is the deterministic render and ``review_status``
records why. The disclaimer is present on every branch.
"""

from __future__ import annotations

import re
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
from genome_firewall.report.reviewer import published_percents_grounded, review_narrative
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
    """True only when a caveat near-restates the appended lab-confirmation disclaimer, so the
    model's helpful duplicate is dropped while a *distinct* clinical caveat is preserved.

    The bug (issue #45-C) was the first conjunct: substring ``"confirm"`` also matched
    ``"confirmed"``, so a real hedge ('the blaKPC allele could not be confirmed -- laboratory
    re-testing advised') was wrongly dropped. Fixed with a word boundary (``\bconfirm\b`` does
    not fire on 'confirmed') and anchored on the canonical's 'result' skeleton, so a
    specific-finding hedge naming no 'result' is kept. The lab conjunct stays broad ('laborator'
    OR 'susceptibility test') so a 'laboratory testing' restatement is still de-duplicated. A
    paraphrase omitting the skeleton is not dropped -- at worst a cosmetic double disclaimer, not
    a lost caveat; the canonical disclaimer from ``report.disclaimer`` still stands (rule #4).
    """
    lowered = caveat.lower()
    return (
        re.search(r"\bconfirm\b", lowered) is not None
        and "result" in lowered
        and ("laborator" in lowered or "susceptibility test" in lowered)
    )


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

    flattened = _flatten(section, report)
    if not published_percents_grounded(flattened, report):
        # Defense-in-depth tripwire (#45-A): the accepted narrative serialised to a percent absent
        # from the report's own numbers. Fail closed to the deterministic template rather than
        # publish it, keeping the review verdict for provenance.
        return _template_envelope(
            report,
            "llm_output_rejected",
            error="published narrative contains an ungrounded percent",
            grounding=outcome.verdict,
        )
    report_with_narrative = _with_summary(report, flattened)
    return NarrativeEnvelope(
        report=report_with_narrative,
        review_status="llm_output_accepted",
        source="llm",
        grounding=outcome.verdict,
    )
