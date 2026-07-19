"""Deterministic, zero-LLM decision-report builder (EPIC 4, issue #23).

Assembles a complete ``GenomeReport`` straight from predictor primitives + AMRFinderPlus-derived
features. This is the MVP core **and** the guaranteed demo/fallback path: it must work
end-to-end with no LLM and no API key. The LLM narrative (EPIC 5) is strictly additive and
receives the frozen report produced here.

Verdict composition mirrors the predictor contract:
  * deterministic gate fired -> forced ``likely_to_fail`` at fixed known-mechanism confidence
    (ADR-0018); the gate is authoritative and short-circuits the model.
  * otherwise the conformal set maps to the verdict (the no-call contract), with calibrated
    confidence derived from the model's resistant probability.
  * min-n insufficient data or an off-panel antibiotic -> a first-class no-call.
"""

from __future__ import annotations

from genome_firewall.constants import KNOWN_MECHANISM_CONFIDENCE
from genome_firewall.predictor.target_gate import evaluate_gate
from genome_firewall.report.evidence import assemble_evidence
from genome_firewall.report.inputs import DrugPredictionInput, GenomePredictionInputs
from genome_firewall.schemas import (
    AntibioticPrediction,
    GenomeReport,
    Verdict,
    verdict_for_conformal_set,
)


def _no_call_row(antibiotic: str, *, target_present: bool | None) -> AntibioticPrediction:
    """A first-class no-call with no positive signal (off-panel or insufficient data)."""
    return AntibioticPrediction(
        antibiotic=antibiotic,
        verdict="no_call",
        calibrated_confidence=0.0,
        evidence_category="no_signal",
        supporting_features=(),
        evidence=(),
        target_present=target_present,
        conformal_set=None,
    )


def _model_confidence(verdict: Verdict, probability_resistant: float) -> float:
    """Calibrated confidence in the majority direction of the verdict."""
    if verdict == "likely_to_fail":
        return probability_resistant
    if verdict == "likely_to_work":
        return 1.0 - probability_resistant
    # no_call: report how sure the model was of its (non-decisive) leaning.
    return max(probability_resistant, 1.0 - probability_resistant)


def _build_row(drug: DrugPredictionInput) -> AntibioticPrediction:
    gate = evaluate_gate(drug.antibiotic, drug.vector)
    target_present = gate.target_present

    # Off-panel antibiotic: nothing the predictor covers -> no-call.
    if target_present is None:
        return _no_call_row(drug.antibiotic, target_present=None)

    # Per-drug min-n gate tripped upstream -> data-driven no-call (ADR-0004).
    if drug.insufficient_data:
        return _no_call_row(drug.antibiotic, target_present=target_present)

    # Deterministic known-mechanism gate fired: authoritative, short-circuits the model.
    if gate.result.fired:
        bundle = assemble_evidence(drug.antibiotic, drug.vector, gate_fired=True)
        forced = gate.result.forced_verdict
        assert forced is not None  # invariant: a fired gate always carries a forced verdict
        return AntibioticPrediction(
            antibiotic=drug.antibiotic,
            verdict=forced,
            calibrated_confidence=KNOWN_MECHANISM_CONFIDENCE,
            evidence_category=bundle.category,
            supporting_features=bundle.supporting_features,
            evidence=bundle.evidence,
            target_present=True,
            conformal_set=None,
        )

    # Model-driven row: verdict from the conformal set, confidence from the calibrated model.
    if drug.conformal_set is None:
        # No gate hit and no conformal set -> we cannot compose a verdict; abstain.
        return _no_call_row(drug.antibiotic, target_present=target_present)

    verdict = verdict_for_conformal_set(drug.conformal_set.labels)
    model_version = drug.model_prediction.model_version if drug.model_prediction else None
    bundle = assemble_evidence(
        drug.antibiotic,
        drug.vector,
        gate_fired=False,
        model_top_features=drug.model_top_features,
        model_version=model_version,
    )
    probability = drug.model_prediction.probability_resistant if drug.model_prediction else 0.0
    confidence = _model_confidence(verdict, probability) if drug.model_prediction else 0.0
    return AntibioticPrediction(
        antibiotic=drug.antibiotic,
        verdict=verdict,
        calibrated_confidence=confidence,
        evidence_category=bundle.category,
        supporting_features=bundle.supporting_features,
        evidence=bundle.evidence,
        target_present=target_present,
        conformal_set=drug.conformal_set,
    )


def build_report(inputs: GenomePredictionInputs) -> GenomeReport:
    """Assemble the complete, deterministic ``GenomeReport`` for one genome.

    Zero LLM calls. The disclaimer defaults to the canonical constant (validated by the schema),
    and ``narrative_summary`` stays ``None`` -- the additive LLM narrative fills it later.
    """
    predictions = tuple(_build_row(drug) for drug in inputs.drugs)
    return GenomeReport(genome_id=inputs.genome_id, predictions=predictions)
