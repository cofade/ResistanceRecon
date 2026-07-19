"""Module 03a — Decision Report: deterministic report builder (zero-LLM MVP core and
demo fallback) plus an additive, strictly grounded LLM narrative sub-pipeline."""

from __future__ import annotations

from genome_firewall.report.builder import build_report
from genome_firewall.report.inputs import DrugPredictionInput, GenomePredictionInputs
from genome_firewall.report.narrative import render_deterministic_narrative
from genome_firewall.report.pipeline import NarrativeEnvelope, narrate_report

__all__ = [
    "DrugPredictionInput",
    "GenomePredictionInputs",
    "NarrativeEnvelope",
    "build_report",
    "narrate_report",
    "render_deterministic_narrative",
]
