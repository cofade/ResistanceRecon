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
from genome_firewall.schemas import AntibioticPrediction, GenomeReport

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


def _bound_narrative_violation(
    drug: str, row: AntibioticPrediction, prose_lower: str
) -> str | None:
    """A single drug's own narrative: it may assert only THAT drug's verdict, and use causal
    language only if that drug's evidence is a known mechanism. Attribution is exact (the entry
    is, by contract, about this one drug) -- no proximity guessing."""
    own_verdict = _VERDICT_LABEL[row.verdict]
    for phrase in _VERDICT_PHRASES:
        if phrase in prose_lower and phrase != own_verdict:
            return (
                f"narrative for {drug} asserts verdict '{phrase}', but its verdict is "
                f"'{own_verdict}'"
            )
    if row.evidence_category != "known_mechanism":
        for phrase in _CAUSAL_PHRASES:
            if phrase in prose_lower:
                return (
                    f"narrative for {drug} uses causal language ('{phrase}'), but its evidence is "
                    f"{row.evidence_category}, not a known mechanism"
                )
    return None


def _free_text_violation(where: str, prose_lower: str) -> str | None:
    """The free-text summary/caveats are overview prose. Per-drug verdict and causal claims belong
    in the per-antibiotic narratives (where attribution is exact), so any verdict or causal phrase
    here is rejected outright -- unambiguous, with no proximity guessing that a plural/aggregate
    sentence ("both are likely to work") could defeat."""
    for phrase in _VERDICT_PHRASES:
        if phrase in prose_lower:
            return (
                f"{where} states a per-drug verdict ('{phrase}'); verdicts belong in the "
                "per-antibiotic narrative"
            )
    for phrase in _CAUSAL_PHRASES:
        if phrase in prose_lower:
            return (
                f"{where} states a causal claim ('{phrase}'); mechanism claims belong in the "
                "per-antibiotic narrative"
            )
    return None


def deterministic_precheck(
    section: NLReportSection,
    report: GenomeReport,
    retrieval: Mapping[str, Sequence[RetrievedChunk]],
) -> tuple[bool, str]:
    """Reject fabricated drugs/numbers/verdicts and mis-attributed causal language.

    Per-drug verdict/causal claims are validated only where attribution is exact -- inside each
    drug's own per-antibiotic narrative (bound to that drug). The free-text summary/caveats may
    not state a verdict or causal phrase at all, so no proximity heuristic (which a plural sentence
    could defeat) is ever load-bearing.
    """
    by_drug: dict[str, AntibioticPrediction] = {p.antibiotic: p for p in report.predictions}
    evaluated = set(by_drug)
    canonical = render_deterministic_narrative(report)
    chunk_text = " ".join(c.chunk.text for chunks in retrieval.values() for c in chunks)
    allowed_numbers = _numbers(f"{canonical}\n{chunk_text}".lower())
    report_numbers = _numbers(canonical.lower())

    prose = _section_prose(section).lower()

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

    # (3) Per-drug narratives: verdict + causal language bound to their own drug (exact).
    for drug_narrative in section.per_antibiotic:
        row = by_drug.get(drug_narrative.antibiotic)
        if row is None:
            continue
        violation = _bound_narrative_violation(
            drug_narrative.antibiotic, row, drug_narrative.narrative.lower()
        )
        if violation:
            return False, violation

    # (4) Free-text summary/caveats: no verdict or causal phrase permitted at all.
    for where, field in [("summary", section.summary), *[("caveat", c) for c in section.caveats]]:
        violation = _free_text_violation(where, field.lower())
        if violation:
            return False, violation

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
