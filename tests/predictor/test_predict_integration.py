"""PR-B end-to-end integration test (issue #22): synthetic cohort -> train_and_register (real
orchestration) -> PredictorRegistry.load -> predict_genome. Asserts the gate/model/no-call
composition, evidence categories, conformal sets, and the typed compat error. Offline; no
Docker, no network."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest
from train_predictor import train_and_register

from genome_firewall.features.feature_matrix import assemble_feature_matrix
from genome_firewall.features.vocabulary import build_vocabulary
from genome_firewall.predictor.errors import AmrfinderDbVersionMismatchError
from genome_firewall.predictor.model_registry import STATUS_TRAINED, PredictorRegistry
from genome_firewall.predictor.predict import predict_genome
from tests.predictor.conftest import SyntheticCohort


def _labels_frame(labels: dict[str, dict[str, str]]) -> pd.DataFrame:
    rows = [
        {
            "genome_id": gid,
            "antibiotic": drug,
            "sir": "Resistant" if side == "R" else "Susceptible",
        }
        for drug, mapping in labels.items()
        for gid, side in mapping.items()
    ]
    return pd.DataFrame(rows)


@pytest.mark.integration
def test_prb_train_register_predict(synthetic_cohort: SyntheticCohort, tmp_path: Path) -> None:
    vectors, labels, metadata = synthetic_cohort
    schema = build_vocabulary(vectors, amrfinder_db_version="2026-05-15.1")
    matrix = assemble_feature_matrix(vectors, schema)
    vector_by_id = {v.genome_id: v for v in vectors}

    summary = train_and_register(
        matrix,
        schema,
        _labels_frame(labels),
        metadata,
        vector_by_id,
        models_dir=tmp_path,
        alpha=0.10,
    )
    drug_summaries = summary["drugs"]
    assert isinstance(drug_summaries, dict)
    assert drug_summaries["gentamicin"]["status"] == STATUS_TRAINED
    assert drug_summaries["ciprofloxacin"]["status"] != STATUS_TRAINED  # thin -> insufficient

    registry = PredictorRegistry.load(tmp_path)
    assert registry.status("gentamicin") == STATUS_TRAINED

    # A carbapenemase-positive genome (within-ST index 0) fires the meropenem gate.
    carb_genome = next(g for g, v in vector_by_id.items() if "blaKPC-2" in v.gene_presence)
    predictions = predict_genome(vector_by_id[carb_genome], registry)
    by_drug = {p.antibiotic: p for p in predictions}
    assert len(predictions) == 5

    mero = by_drug["meropenem"]
    assert mero.verdict == "likely_to_fail"
    assert mero.evidence_category == "known_mechanism"
    assert mero.conformal_set is None

    genta = by_drug["gentamicin"]
    assert genta.evidence_category == "statistical_association"
    assert genta.conformal_set is not None
    assert genta.evidence  # non-empty, cited
    assert 0.0 <= genta.calibrated_confidence <= 1.0

    # For a gate-NEGATIVE genome (no carbapenemase, no QRDR mutation), an insufficient-data drug
    # is an honest no_call; the meropenem MODEL (not the gate) serves it -- one-directional, so
    # the absence of a resistance marker is never gate-forced to a known-mechanism call.
    clean_genome = next(
        g
        for g, v in vector_by_id.items()
        if "blaKPC-2" not in v.gene_presence and not v.point_mutations
    )
    clean_predictions = {
        p.antibiotic: p for p in predict_genome(vector_by_id[clean_genome], registry)
    }
    cipro = clean_predictions["ciprofloxacin"]
    assert cipro.verdict == "no_call"
    assert cipro.evidence_category == "no_signal"
    assert clean_predictions["meropenem"].evidence_category != "known_mechanism"

    # Compatibility: a genome annotated under a different DB version fails loud.
    bad = vector_by_id[carb_genome].model_copy(update={"amrfinder_db_version": "2099-01-01.9"})
    with pytest.raises(AmrfinderDbVersionMismatchError):
        predict_genome(bad, registry)
