"""Manual demo of the EPIC 4/5 report + grounded LLM narrative path.

No UI or API exists yet (those are later epics), so this is the runnable entry point for the
EPIC 5 narrative: it builds a representative multi-verdict ``GenomeReport`` and runs the additive
narrative pipeline through whatever LLM is configured in ``.env`` (the real OpenAI backend when
``OPENAI_API_KEY`` is set, otherwise the deterministic template). It prints the envelope
provenance and the final narrative so a human can judge clinical wording quality -- the one thing
the automated gates cannot.

Usage:
    uv run python scripts/demo_report_narrative.py
"""

from __future__ import annotations

import time

from genome_firewall.kb.evidence_rag import EvidenceRAG
from genome_firewall.llm.factory import make_client
from genome_firewall.llm.settings import LLMSettings
from genome_firewall.report.builder import build_report
from genome_firewall.report.inputs import DrugPredictionInput, GenomePredictionInputs
from genome_firewall.report.pipeline import narrate_report
from genome_firewall.schemas import (
    ConformalSet,
    GenomeFeatureVector,
    GenomeReport,
    ModelPrediction,
)


def _vector(
    genes: dict[str, bool] | None = None, subclass: dict[str, str] | None = None
) -> GenomeFeatureVector:
    return GenomeFeatureVector(
        genome_id="573.demo",
        schema_version="1.0.0",
        amrfinder_db_version="2026-05-15.1",
        gene_presence=genes or {},
        gene_drug_subclass=subclass or {},
    )


def _demo_report() -> GenomeReport:
    """A representative panel: a known-mechanism fail, a model-driven fail, a susceptible work."""
    drugs = (
        DrugPredictionInput(
            antibiotic="meropenem",
            vector=_vector({"blaKPC-2": True}, {"blaKPC-2": "CARBAPENEM"}),
        ),
        DrugPredictionInput(
            antibiotic="gentamicin",
            vector=_vector({"aac(3)-IIa": True}, {"aac(3)-IIa": "GENTAMICIN"}),
            model_prediction=ModelPrediction(probability_resistant=0.82, model_version="lr-v1"),
            conformal_set=ConformalSet(labels=("R",), alpha=0.1),
            model_top_features=("eng:has_ame", "aac(3)-IIa"),
        ),
        DrugPredictionInput(
            antibiotic="ceftriaxone",
            vector=_vector(),
            model_prediction=ModelPrediction(probability_resistant=0.04, model_version="lr-v1"),
            conformal_set=ConformalSet(labels=("S",), alpha=0.1),
        ),
    )
    return build_report(GenomePredictionInputs(genome_id="573.demo", drugs=drugs))


def main() -> None:
    settings = LLMSettings()
    client = make_client(settings)
    backend = "real OpenAI" if client is not None else "None -> deterministic template"
    print(
        f"model={settings.openai_model!r} "
        f"reasoning_effort={settings.openai_reasoning_effort!r} "
        f"key_present={bool(settings.openai_api_key)} backend={backend}"
    )

    report = _demo_report()
    retriever = EvidenceRAG.from_seed()

    start = time.perf_counter()
    envelope = narrate_report(report, client=client, retriever=retriever)
    elapsed = time.perf_counter() - start

    print(f"\n=== narrate_report finished in {elapsed:.1f}s ===")
    print(f"review_status={envelope.review_status}  source={envelope.source}")
    if envelope.error:
        print(f"error={envelope.error}")
    if envelope.grounding is not None:
        print(
            f"grounding: overall_pass={envelope.grounding.overall_pass} "
            f"score={envelope.grounding.grounding_score}"
        )
    print("\n----- narrative_summary -----")
    print(envelope.report.narrative_summary)


if __name__ == "__main__":
    main()
