"""Shared fixtures for report-layer tests: builders for GenomeFeatureVector and the
decoupled DrugPredictionInput/GenomePredictionInputs contract. Deterministic, no I/O.
"""

from __future__ import annotations

from genome_firewall.report.inputs import DrugPredictionInput, GenomePredictionInputs
from genome_firewall.schemas import ConformalSet, GenomeFeatureVector, ModelPrediction

_DB_VERSION = "2026-05-15.1"


def vector(
    genome_id: str = "g1",
    *,
    gene_presence: dict[str, bool] | None = None,
    gene_drug_subclass: dict[str, str] | None = None,
    point_mutations: dict[str, bool] | None = None,
    point_mutation_disrupt: dict[str, bool] | None = None,
) -> GenomeFeatureVector:
    return GenomeFeatureVector(
        genome_id=genome_id,
        schema_version="1.0.0",
        amrfinder_db_version=_DB_VERSION,
        gene_presence=gene_presence or {},
        gene_drug_subclass=gene_drug_subclass or {},
        point_mutations=point_mutations or {},
        point_mutation_disrupt=point_mutation_disrupt or {},
    )


def meropenem_gate_input(genome_id: str = "g1") -> DrugPredictionInput:
    """A carbapenemase (blaKPC-2) genome: the deterministic gate fires -> known-mechanism fail."""
    return DrugPredictionInput(
        antibiotic="meropenem",
        vector=vector(
            genome_id,
            gene_presence={"blaKPC-2": True},
            gene_drug_subclass={"blaKPC-2": "CARBAPENEM"},
        ),
    )


def gentamicin_model_input(genome_id: str = "g1") -> DrugPredictionInput:
    """AME-only genome: gate does NOT fire; verdict from the model + conformal {R}."""
    return DrugPredictionInput(
        antibiotic="gentamicin",
        vector=vector(
            genome_id,
            gene_presence={"aac(3)-IIa": True},
            gene_drug_subclass={"aac(3)-IIa": "GENTAMICIN"},
        ),
        model_prediction=ModelPrediction(probability_resistant=0.82, model_version="lr-v1"),
        conformal_set=ConformalSet(labels=("R",), alpha=0.1),
        model_top_features=("eng:has_ame", "aac(3)-IIa"),
    )


def ceftriaxone_susceptible_input(genome_id: str = "g1") -> DrugPredictionInput:
    """A clean genome: no resistance markers, conformal {S} -> likely-to-work / no_signal."""
    return DrugPredictionInput(
        antibiotic="ceftriaxone",
        vector=vector(genome_id),
        model_prediction=ModelPrediction(probability_resistant=0.04, model_version="lr-v1"),
        conformal_set=ConformalSet(labels=("S",), alpha=0.1),
    )


def ciprofloxacin_insufficient_input(genome_id: str = "g1") -> DrugPredictionInput:
    """Below the per-drug min-n gate -> data-driven no-call."""
    return DrugPredictionInput(
        antibiotic="ciprofloxacin", vector=vector(genome_id), insufficient_data=True
    )


def make_prediction_inputs(genome_id: str = "g1") -> GenomePredictionInputs:
    """A representative multi-drug bundle spanning gate / model / susceptible / insufficient."""
    return GenomePredictionInputs(
        genome_id=genome_id,
        drugs=(
            meropenem_gate_input(genome_id),
            gentamicin_model_input(genome_id),
            ceftriaxone_susceptible_input(genome_id),
            ciprofloxacin_insufficient_input(genome_id),
        ),
    )
