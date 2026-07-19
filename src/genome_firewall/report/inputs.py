"""Decoupled input contract for the deterministic report builder (EPIC 4, issue #23).

The builder consumes only primitive predictor-output schemas that already exist on ``main``
(``ModelPrediction``, ``ConformalSet``) plus the genome's ``GenomeFeatureVector`` -- it never
imports the composite ``predictor.predict`` output (EPIC 3 PR-B, still in flight), so this
module can be built and tested against fixtures without depending on unmerged code.

Defined here rather than in ``schemas.py`` deliberately: ``schemas.py`` is the frozen
cross-epic contract, and a per-drug *builder input* is an internal report-layer concern.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from genome_firewall.schemas import ConformalSet, GenomeFeatureVector, ModelPrediction


class DrugPredictionInput(BaseModel):
    """Everything the builder needs to assemble one antibiotic row, for one genome.

    ``model_top_features`` are the feature names the calibrated model weighted most for this
    (genome, antibiotic) call -- supplied by the caller (in production, ``predict.py``; in
    tests, a fixture). They substantiate ``statistical_association`` evidence without the
    builder importing the model. ``insufficient_data`` is set when the per-drug min-n gate
    (ADR-0004) tripped upstream, forcing a data-driven no-call.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    antibiotic: str
    vector: GenomeFeatureVector
    model_prediction: ModelPrediction | None = None
    conformal_set: ConformalSet | None = None
    model_top_features: tuple[str, ...] = ()
    insufficient_data: bool = False


class GenomePredictionInputs(BaseModel):
    """The per-genome bundle handed to :func:`genome_firewall.report.builder.build_report`."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    genome_id: str
    drugs: tuple[DrugPredictionInput, ...]
