"""Integration-test shape #5: frozen report -> narrator + reviewer -> accepted, OR fail-closed
to the deterministic template. Driven by committed LLM fixtures + MockLLMClient (no key/network).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from genome_firewall.constants import LAB_CONFIRMATION_DISCLAIMER
from genome_firewall.kb.embedder import HashingBagOfWordsEmbedder
from genome_firewall.kb.evidence_rag import EvidenceRAG
from genome_firewall.llm.mock import MockLLMClient
from genome_firewall.report.builder import build_report
from genome_firewall.report.inputs import GenomePredictionInputs
from genome_firewall.report.narrative import render_deterministic_narrative
from genome_firewall.report.pipeline import narrate_report
from tests.report.conftest import ceftriaxone_susceptible_input, meropenem_gate_input

_FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "llm"


def _fixture(name: str) -> str:
    return (_FIXTURES / name).read_text(encoding="utf-8")


def _report() -> object:
    return build_report(
        GenomePredictionInputs(
            genome_id="573.10001",
            drugs=(meropenem_gate_input("573.10001"), ceftriaxone_susceptible_input("573.10001")),
        )
    )


@pytest.mark.integration
def test_grounded_narrative_is_accepted_end_to_end() -> None:
    report = _report()
    client = MockLLMClient(
        {
            "report_narrative": _fixture("narrator_grounded.json"),
            "report_review": _fixture("reviewer_pass.json"),
        }
    )
    retriever = EvidenceRAG.from_seed(embedder=HashingBagOfWordsEmbedder())
    env = narrate_report(report, client=client, retriever=retriever)  # type: ignore[arg-type]

    assert env.review_status == "llm_output_accepted"
    assert env.source == "llm"
    assert env.grounding is not None and env.grounding.overall_pass
    summary = env.report.narrative_summary or ""
    assert "Meropenem is LIKELY TO FAIL" in summary
    assert LAB_CONFIRMATION_DISCLAIMER in summary  # disclaimer on the LLM path


@pytest.mark.integration
def test_fabricated_narrative_fails_closed_to_deterministic_template() -> None:
    report = _report()
    client = MockLLMClient(
        {
            "report_narrative": _fixture("narrator_fabricated_number.json"),
            "report_review": _fixture(
                "reviewer_pass.json"
            ),  # judge would pass, but pre-check won't
        }
    )
    env = narrate_report(report, client=client)  # type: ignore[arg-type]

    assert env.review_status == "llm_output_rejected"
    assert env.source == "template"
    assert env.report.narrative_summary == render_deterministic_narrative(report)  # type: ignore[arg-type]
    assert LAB_CONFIRMATION_DISCLAIMER in (env.report.narrative_summary or "")
