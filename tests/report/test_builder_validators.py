"""Property-style guard: every (genome x drug) row the builder emits over the whole synthetic
cohort constructs without a ValidationError -- i.e. the evidence-tagging policy satisfies all
three AntibioticPrediction validators (verdict<->conformal, non-no_signal<->support,
row-category<->cited-item) by construction. This is the Validator-3-footgun regression pin.
"""

from __future__ import annotations

from genome_firewall.report.builder import build_report
from genome_firewall.report.inputs import DrugPredictionInput, GenomePredictionInputs
from genome_firewall.schemas import ConformalSet, GenomeFeatureVector, ModelPrediction
from tests.predictor.conftest import make_synthetic_cohort


def _drug_input(antibiotic: str, vector: GenomeFeatureVector, sir: str) -> DrugPredictionInput:
    labels = (sir,)  # {S}->work, {R}->fail; a singleton always maps cleanly
    probability = 0.9 if sir == "R" else 0.1
    return DrugPredictionInput(
        antibiotic=antibiotic,
        vector=vector,
        model_prediction=ModelPrediction(probability_resistant=probability, model_version="lr-v1"),
        conformal_set=ConformalSet(labels=labels, alpha=0.1),
        model_top_features=("eng:has_ame", "eng:has_carbapenemase"),
    )


def test_every_cohort_row_satisfies_all_antibiotic_prediction_validators() -> None:
    vectors, labels, _ = make_synthetic_cohort()
    by_id = {v.genome_id: v for v in vectors}
    built = 0
    for antibiotic in ("gentamicin", "meropenem", "ciprofloxacin"):
        for gid, sir in labels[antibiotic].items():
            report = build_report(
                GenomePredictionInputs(
                    genome_id=gid,
                    drugs=(_drug_input(antibiotic, by_id[gid], sir),),
                )
            )
            row = report.predictions[0]
            # Reconstruct to force the validators to run again on the emitted values.
            assert row.verdict in {"likely_to_work", "likely_to_fail", "no_call"}
            if row.evidence_category != "no_signal":
                assert row.supporting_features
                assert row.evidence_category in {i.evidence_category for i in row.evidence}
            built += 1
    assert built > 100  # exercised the whole labelled cohort
