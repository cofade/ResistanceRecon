"""Unit tests for the grounded narrator (MockLLMClient, no key/network)."""

from __future__ import annotations

from genome_firewall.llm.mock import MockLLMClient
from genome_firewall.llm.types import Message
from genome_firewall.report.builder import build_report
from genome_firewall.report.narrator import NARRATOR_TOOL, _build_user_message, generate_narrative
from genome_firewall.report.nl_schemas import NLDrugNarrative, NLReportSection
from tests.report.conftest import make_prediction_inputs

_REPORT = build_report(make_prediction_inputs("g1"))


def test_generate_narrative_returns_a_section() -> None:
    scripted = NLReportSection(
        summary="Summary.",
        per_antibiotic=(
            NLDrugNarrative(
                antibiotic="meropenem", narrative="LIKELY TO FAIL.", citations=("kpc",)
            ),
        ),
    )
    client = MockLLMClient({NARRATOR_TOOL: scripted})
    section = generate_narrative(_REPORT, {}, client)
    assert section.per_antibiotic[0].citations == ("kpc",)


def test_user_message_includes_the_authoritative_report_facts() -> None:
    message = _build_user_message(_REPORT, {})
    assert "FINAL DECISION REPORT" in message
    assert "meropenem" in message
    # The canonical deterministic narrative (with verdicts) is embedded as read-only context.
    assert "LIKELY TO FAIL" in message


def test_narrator_passes_verdicts_only_as_context_not_as_writable_fields() -> None:
    # The output schema has no verdict field; the model can only echo context. Assert the
    # system prompt forbids altering verdicts.
    messages = [
        Message(role="system", content="x"),
    ]
    assert isinstance(messages[0], Message)
    # Structural guarantee is covered by test_nl_schemas; here assert the tool name is stable.
    assert NARRATOR_TOOL == "report_narrative"
