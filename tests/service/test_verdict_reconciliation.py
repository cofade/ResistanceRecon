"""Safety invariant (issue #7): the report path (service.to_prediction_inputs -> build_report)
never disagrees with the sovereign predictor path (predict_genome, golden rule #1) on any
verdict or confidence. build_report re-derives rows via the decoupled report.inputs contract
and tags evidence per ADR-0020; this pins those rows to predict_genome so the two frozen paths
can never silently drift. Offline; deterministic.
"""

from __future__ import annotations

import pytest

from genome_firewall import service
from genome_firewall.predictor.predict import predict_genome
from genome_firewall.report import build_report
from tests._demo import demo_vector, load_demo_registry


@pytest.mark.parametrize("genome_id", ["573.10001", "573.10002"])
def test_report_verdicts_match_sovereign_predictor(genome_id: str) -> None:
    registry = load_demo_registry()
    vector = demo_vector(genome_id)

    sovereign = {p.antibiotic: p for p in predict_genome(vector, registry)}
    report = build_report(service.to_prediction_inputs(vector, registry))

    assert {p.antibiotic for p in report.predictions} == set(sovereign)
    for row in report.predictions:
        gold = sovereign[row.antibiotic]
        assert row.verdict == gold.verdict, row.antibiotic
        assert row.calibrated_confidence == pytest.approx(gold.calibrated_confidence), (
            row.antibiotic
        )
        assert (row.conformal_set.labels if row.conformal_set else ()) == (
            gold.conformal_set.labels if gold.conformal_set else ()
        )
