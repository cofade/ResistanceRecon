"""Integration-test shape #2+#3+#5 chained (issue #7): FASTA -> MockAnnotator -> features ->
predictor -> build_report -> narrate_report -> NarrativeEnvelope, through the one in-process
orchestrator both the API and the UI call (service.analyze_genome, ADR-0022). Offline: bundled
demo fixtures + MockLLMClient, no Docker, no key, no network.
"""

from __future__ import annotations

import pytest

from genome_firewall import service
from genome_firewall.constants import LAB_CONFIRMATION_DISCLAIMER, SUPPORTED_ANTIBIOTICS
from genome_firewall.kb.embedder import HashingBagOfWordsEmbedder
from genome_firewall.kb.evidence_rag import EvidenceRAG
from genome_firewall.llm.mock import MockLLMClient
from genome_firewall.report.narrative import render_deterministic_narrative
from tests._demo import demo_report, load_demo_registry, passing_review, passing_section


def _analyze(genome_id: str, **kwargs: object):
    return service.analyze_genome(
        service.DEMO_FASTA_PATH,
        genome_id=genome_id,
        annotator=service.default_annotator(),
        registry=load_demo_registry(),
        **kwargs,  # type: ignore[arg-type]
    )


@pytest.mark.integration
def test_llm_disabled_path_serves_deterministic_template() -> None:
    envelope = _analyze("573.10001", client=None)

    assert envelope.review_status == "llm_disabled"
    assert envelope.source == "template"
    # Full panel, in order -- the real predictor ran, not a stub.
    assert tuple(p.antibiotic for p in envelope.report.predictions) == SUPPORTED_ANTIBIOTICS
    # The gate fired for ciprofloxacin on this genome (double QRDR) -> a known-mechanism verdict.
    cipro = next(p for p in envelope.report.predictions if p.antibiotic == "ciprofloxacin")
    assert cipro.verdict == "likely_to_fail"
    assert cipro.evidence_category == "known_mechanism"
    summary = envelope.report.narrative_summary or ""
    assert LAB_CONFIRMATION_DISCLAIMER in summary
    assert summary == render_deterministic_narrative(
        envelope.report.model_copy(update={"narrative_summary": None})
    )


@pytest.mark.integration
def test_grounded_llm_narrative_is_accepted_end_to_end() -> None:
    report = demo_report("573.10001")
    client = MockLLMClient(
        {"report_narrative": passing_section(report), "report_review": passing_review()}
    )
    retriever = EvidenceRAG.from_seed(embedder=HashingBagOfWordsEmbedder())

    envelope = _analyze("573.10001", client=client, retriever=retriever)

    assert envelope.review_status == "llm_output_accepted"
    assert envelope.source == "llm"
    assert envelope.grounding is not None and envelope.grounding.overall_pass
    assert LAB_CONFIRMATION_DISCLAIMER in (envelope.report.narrative_summary or "")


@pytest.mark.integration
def test_llm_narrator_error_fails_closed_to_template() -> None:
    # An empty MockLLMClient has no scripted narrator response -> LLMRefusalError -> fail closed.
    envelope = _analyze("573.10001", client=MockLLMClient({}))

    assert envelope.review_status == "llm_output_rejected"
    assert envelope.source == "template"
    assert envelope.error is not None
    summary = envelope.report.narrative_summary or ""
    assert LAB_CONFIRMATION_DISCLAIMER in summary


@pytest.mark.integration
def test_clean_genome_reports_no_resistance_signal() -> None:
    envelope = _analyze("573.10002", client=None)

    categories = {p.evidence_category for p in envelope.report.predictions}
    assert categories == {"no_signal"}  # a clean genome: nothing gated, nothing weighted
    assert "likely_to_fail" not in {p.verdict for p in envelope.report.predictions}
    assert LAB_CONFIRMATION_DISCLAIMER in (envelope.report.narrative_summary or "")
