"""Safety invariant (issue #7; senior review P0/P1): the report path (service.to_prediction_inputs
-> build_report) never disagrees with the sovereign predictor path (predict_genome, golden rule #1)
on any served VERDICT, CONFIDENCE, or CONFORMAL SET. build_report re-derives rows via the decoupled
report.inputs contract; this pins those rows to predict_genome across the model-driven, gate-fired,
and untrained-gate-firing branches so the two frozen paths can never silently drift on a verdict.

It deliberately does NOT assert evidence_category equality: the two paths differ there BY DESIGN
(predict.py tags model rows statistical_association; build_report applies the stronger ADR-0020
KNOWN-vs-STATISTICAL rollup -- e.g. a clean genome is statistical_association in predict_genome but
no_signal in build_report). That divergence is the intended reason the report is routed through
build_report; asserting evidence_category equality here would (correctly) fail. See ADR-0022.
"""

from __future__ import annotations

import dataclasses

import pytest

from genome_firewall import service
from genome_firewall.predictor.model_registry import PredictorRegistry
from genome_firewall.predictor.predict import predict_genome
from genome_firewall.report import build_report
from genome_firewall.schemas import GenomeFeatureVector
from tests._demo import demo_vector, load_demo_registry


def _without(registry: PredictorRegistry, drug: str) -> PredictorRegistry:
    return dataclasses.replace(
        registry, drugs={k: v for k, v in registry.drugs.items() if k != drug}
    )


def _ame_vector() -> GenomeFeatureVector:
    """Strong aminoglycoside-modifying enzymes but NO 16S RMTase: the gentamicin gate does not fire
    and the calibrated model drives a {R} conformal set -> a MODEL-driven likely_to_fail, which
    exercises the report builder's `return probability_resistant` confidence branch (builder.py:47),
    the single highest-stakes verdict (a BLOCK on model evidence) and the one branch the two demo
    genomes never produce."""
    return GenomeFeatureVector(
        genome_id="synthetic-ame",
        schema_version="1.0.0",
        amrfinder_db_version="2026-05-15.1",
        gene_presence={
            "aac(3)-IIe": True,
            "aac(6')-Ib'": True,
            "ant(2'')-Ia": True,
            "aadA1": True,
        },
    )


def _scenarios() -> list[tuple[str, GenomeFeatureVector, PredictorRegistry]]:
    reg = load_demo_registry()
    return [
        ("573.10001 full (gate-fire + model + ambiguous)", demo_vector("573.10001"), reg),
        ("573.10002 clean (all no-signal)", demo_vector("573.10002"), reg),
        ("synthetic AME (model-driven likely_to_fail)", _ame_vector(), reg),
        (
            "untrained ciprofloxacin, gate FIRES (P0)",
            demo_vector("573.10001"),
            _without(reg, "ciprofloxacin"),
        ),
        ("untrained gentamicin, gate quiet", demo_vector("573.10002"), _without(reg, "gentamicin")),
    ]


_SCENARIOS = _scenarios()


@pytest.mark.parametrize(
    "vector,registry", [(v, r) for _label, v, r in _SCENARIOS], ids=[s[0] for s in _SCENARIOS]
)
def test_report_verdicts_match_sovereign_predictor(
    vector: GenomeFeatureVector, registry: PredictorRegistry
) -> None:
    sovereign = {p.antibiotic: p for p in predict_genome(vector, registry)}
    report = build_report(service.to_prediction_inputs(vector, registry))

    assert {p.antibiotic for p in report.predictions} == set(sovereign)
    for row in report.predictions:
        gold = sovereign[row.antibiotic]
        assert row.verdict == gold.verdict, row.antibiotic
        assert row.calibrated_confidence == pytest.approx(gold.calibrated_confidence), (
            row.antibiotic
        )
        gold_labels = gold.conformal_set.labels if gold.conformal_set else ()
        row_labels = row.conformal_set.labels if row.conformal_set else ()
        assert row_labels == gold_labels, row.antibiotic


def test_scenarios_actually_cover_the_high_stakes_branches() -> None:
    """Guard the test's own value: assert the AME scenario really is a model-driven
    likely_to_fail and the P0 scenario really is a gate-fired known_mechanism -- so a future
    model/registry change that stops exercising these branches fails loudly, not vacuously."""
    reg = load_demo_registry()
    ame = {p.antibiotic: p for p in predict_genome(_ame_vector(), reg)}["gentamicin"]
    assert ame.verdict == "likely_to_fail" and ame.evidence_category == "statistical_association"
    p0 = {
        p.antibiotic: p
        for p in predict_genome(demo_vector("573.10001"), _without(reg, "ciprofloxacin"))
    }
    assert p0["ciprofloxacin"].verdict == "likely_to_fail"
    assert p0["ciprofloxacin"].evidence_category == "known_mechanism"
