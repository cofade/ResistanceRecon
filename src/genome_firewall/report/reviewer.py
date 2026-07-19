"""LLM-as-reviewer with a deterministic pre-check that runs BEFORE any LLM call.

The cheap non-LLM check catches the crudest, most consequential failures -- a fabricated drug
name, a fabricated number, a verdict word the report never made, or causal language attached to
a merely-statistical association -- without depending on a judge model that shares a failure
mode with the narrator. Only if the pre-check passes does the LLM judge run. The pipeline fails
closed to the deterministic template whenever ``overall_pass`` is false.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from genome_firewall.constants import SUPPORTED_ANTIBIOTICS
from genome_firewall.kb.retriever import RetrievedChunk
from genome_firewall.llm.client import LLMClient
from genome_firewall.llm.errors import LLMError
from genome_firewall.llm.types import Message
from genome_firewall.report.narrative import render_deterministic_narrative
from genome_firewall.report.nl_schemas import NLReportSection, ReportVerdict
from genome_firewall.schemas import GenomeReport

REVIEWER_TOOL = "report_review"

_NUMBER_RE = re.compile(r"\d+(?:\.\d+)?")
_PERCENT_RE = re.compile(r"(\d+(?:\.\d+)?)\s*%")
_VERDICT_PHRASES = ("likely to work", "likely to fail", "no call")
#: Canonical lower-case verdict phrase per verdict literal (matches narrative.py rendering).
_VERDICT_LABEL: dict[str, str] = {
    "likely_to_work": "likely to work",
    "likely_to_fail": "likely to fail",
    "no_call": "no call",
}
_CAUSAL_PHRASES = (
    "confers resistance",
    "causes resistance",
    "guarantees resistance",
    "due to the presence",
)

_SYSTEM = (
    "You are a strict grounding reviewer. Given a FINAL decision report and a generated "
    "narrative, judge whether every claim in the narrative is supported by the report or a cited "
    "KB chunk, and whether any statistical association was wrongly described as a proven cause. "
    "Do not restate or change any verdict. Output grounding_score in [0,1], a per_claim list, and "
    "overall_pass=false if any claim is unsupported or a statistical signal is described causally."
)


@dataclass(frozen=True)
class ReviewOutcome:
    """The result of reviewing a narrative. ``passed`` gates publication of the LLM prose."""

    passed: bool
    reason: str
    verdict: ReportVerdict | None = None


def _numbers(text: str) -> set[str]:
    return set(_NUMBER_RE.findall(text))


def _section_prose(section: NLReportSection) -> str:
    parts = [section.summary, *section.caveats]
    parts.extend(d.narrative for d in section.per_antibiotic)
    return "\n".join(parts)


def deterministic_precheck(
    section: NLReportSection,
    report: GenomeReport,
    retrieval: Mapping[str, Sequence[RetrievedChunk]],
) -> tuple[bool, str]:
    """Reject fabricated drugs/numbers/verdicts and mis-attributed causal language.

    Every check is bound to the specific drug row it concerns -- a flattened global membership
    test would let a per-drug verdict swap slip through in a mixed-verdict panel (where every
    verdict phrase appears *somewhere* in the report).
    """
    by_drug = {p.antibiotic: p for p in report.predictions}
    evaluated = set(by_drug)
    canonical = render_deterministic_narrative(report)
    canonical_lower = canonical.lower()
    chunk_text = " ".join(c.chunk.text for chunks in retrieval.values() for c in chunks)
    allowed_numbers = _numbers(f"{canonical}\n{chunk_text}".lower())
    report_numbers = _numbers(canonical_lower)

    prose = _section_prose(section).lower()
    summary_prose = "\n".join([section.summary, *section.caveats]).lower()

    # (1) Fabricated numbers. A confidence-shaped number (N%) must match one of the report's OWN
    # numbers, not merely appear somewhere in the retrieved KB text; other numbers may be cited.
    for percent in _PERCENT_RE.findall(prose):
        if percent not in report_numbers:
            return False, f"narrative states a confidence ({percent}%) not present in the report"
    for number in _numbers(prose):
        if number not in allowed_numbers:
            return False, f"narrative contains a number not in the report or citations: {number}"

    # (2) Fabricated drug names: a per-antibiotic entry for a drug not evaluated, or a panel drug
    # named anywhere in the prose but never evaluated in this report.
    for drug_narrative in section.per_antibiotic:
        if drug_narrative.antibiotic not in evaluated:
            return False, (
                f"narrative covers {drug_narrative.antibiotic}, which was not evaluated "
                "in this report"
            )
    for drug in SUPPORTED_ANTIBIOTICS:
        if drug in prose and drug not in evaluated:
            return False, f"narrative discusses {drug}, which was not evaluated in this report"

    # (3) Per-drug verdict binding: a drug's narrative may only assert THAT drug's verdict.
    for drug_narrative in section.per_antibiotic:
        row = by_drug.get(drug_narrative.antibiotic)
        if row is None:
            continue
        own_verdict = _VERDICT_LABEL[row.verdict]
        narrative_lower = drug_narrative.narrative.lower()
        for phrase in _VERDICT_PHRASES:
            if phrase in narrative_lower and phrase != own_verdict:
                return False, (
                    f"narrative asserts '{phrase}' for {drug_narrative.antibiotic}, whose verdict "
                    f"is '{own_verdict}'"
                )
    # The free-text summary/caveats may only use verdict phrases the report actually made.
    for phrase in _VERDICT_PHRASES:
        if phrase in summary_prose and phrase not in canonical_lower:
            return False, f"summary asserts a verdict the report did not make: '{phrase}'"

    # (4) Causal language attached to a non-known-mechanism row -- in its own narrative OR named
    # in the summary/caveats. A statistical association is never described as a proven cause.
    for drug_narrative in section.per_antibiotic:
        row = by_drug.get(drug_narrative.antibiotic)
        if row is None or row.evidence_category == "known_mechanism":
            continue
        if any(phrase in drug_narrative.narrative.lower() for phrase in _CAUSAL_PHRASES):
            return False, (
                f"narrative uses causal language for {drug_narrative.antibiotic}, whose evidence "
                f"is {row.evidence_category}, not a known mechanism"
            )
    summary_has_causal = any(phrase in summary_prose for phrase in _CAUSAL_PHRASES)
    if summary_has_causal:
        for drug, row in by_drug.items():
            if row.evidence_category != "known_mechanism" and drug in summary_prose:
                return False, (
                    f"summary uses causal language for {drug}, whose evidence is "
                    f"{row.evidence_category}, not a known mechanism"
                )

    return True, "deterministic pre-check passed"


def _build_review_message(section: NLReportSection, report: GenomeReport) -> str:
    return (
        "FINAL DECISION REPORT:\n"
        f"{render_deterministic_narrative(report)}\n\n"
        "GENERATED NARRATIVE (JSON):\n"
        f"{section.model_dump_json(indent=2)}"
    )


def review_narrative(
    section: NLReportSection,
    report: GenomeReport,
    retrieval: Mapping[str, Sequence[RetrievedChunk]],
    client: LLMClient,
) -> ReviewOutcome:
    """Run the deterministic pre-check, then (only if it passes) the LLM judge. Fails closed."""
    ok, reason = deterministic_precheck(section, report, retrieval)
    if not ok:
        return ReviewOutcome(passed=False, reason=f"pre-check rejected: {reason}")

    messages = [
        Message(role="system", content=_SYSTEM),
        Message(role="user", content=_build_review_message(section, report)),
    ]
    try:
        verdict = client.complete_structured(
            messages, schema=ReportVerdict, tool_name=REVIEWER_TOOL
        ).parsed
    except LLMError as exc:
        return ReviewOutcome(passed=False, reason=f"reviewer LLM error: {exc}")

    if not verdict.overall_pass:
        return ReviewOutcome(
            passed=False, reason="LLM judge rejected the narrative", verdict=verdict
        )
    return ReviewOutcome(passed=True, reason="grounded and accepted", verdict=verdict)
