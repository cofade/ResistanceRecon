"""Grounded LLM narrator: turns a frozen GenomeReport + retrieved KB citations into
clinician-readable prose. Verdicts/confidence enter only as read-only context; the output
schema (NLReportSection) has no field the model could use to change a verdict.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from genome_firewall.kb.retriever import RetrievedChunk
from genome_firewall.llm.client import LLMClient
from genome_firewall.llm.types import Message
from genome_firewall.report.narrative import render_deterministic_narrative
from genome_firewall.report.nl_schemas import NLReportSection
from genome_firewall.schemas import GenomeReport

NARRATOR_TOOL = "report_narrative"

_SYSTEM = (
    "You are a clinical-microbiology report writer. You explain an ALREADY-FINAL decision "
    "report; you never change, add, or infer a verdict, a confidence value, or a number. "
    "Rules: (1) reference only the verdicts, confidences, and evidence given below; never "
    "invent a drug, gene, or number. (2) Render NO CALL literally as an abstention -- never "
    "soften it into 'probably'. (3) Only describe a resistance mechanism as causing/conferring "
    "resistance when its evidence is a KNOWN resistance mechanism; for a statistical "
    "association say the model weighted it, not that it causes resistance. (4) State each drug's "
    "verdict (LIKELY TO WORK / LIKELY TO FAIL / NO CALL) and any mechanism/causal claim ONLY "
    "inside that drug's per_antibiotic narrative; keep the `summary` and `caveats` as a high-level "
    "overview free of any per-drug verdict phrase or causal claim. (5) Keep it concise. "
    "(6) Do NOT restate the lab-confirmation disclaimer (the 'confirm with laboratory "
    "testing' sentence); the system appends the official disclaimer, so restating it "
    "duplicates it."
)


def _citation_block(chunks: Sequence[RetrievedChunk]) -> str:
    if not chunks:
        return "    (no KB citations retrieved)"
    return "\n".join(
        f"    - [{c.chunk.chunk_id}] {c.chunk.text} (source: {c.chunk.source})" for c in chunks
    )


def _build_user_message(
    report: GenomeReport, retrieval: Mapping[str, Sequence[RetrievedChunk]]
) -> str:
    lines = [
        "FINAL DECISION REPORT (authoritative facts -- do not alter):",
        render_deterministic_narrative(report),
        "",
        "RETRIEVED KB CITATIONS (per antibiotic, for context/citation only):",
    ]
    for prediction in report.predictions:
        lines.append(f"  {prediction.antibiotic}:")
        lines.append(_citation_block(tuple(retrieval.get(prediction.antibiotic, ()))))
    lines.append("")
    lines.append(
        "Write a JSON object: a one-paragraph `summary`, a `per_antibiotic` array of "
        "{antibiotic, narrative, citations}, and optional `caveats`. Cite chunk ids where used."
    )
    return "\n".join(lines)


def generate_narrative(
    report: GenomeReport,
    retrieval: Mapping[str, Sequence[RetrievedChunk]],
    client: LLMClient,
) -> NLReportSection:
    """Produce a grounded natural-language narrative for a frozen report."""
    messages = [
        Message(role="system", content=_SYSTEM),
        Message(role="user", content=_build_user_message(report, retrieval)),
    ]
    return client.complete_structured(
        messages, schema=NLReportSection, tool_name=NARRATOR_TOOL
    ).parsed
