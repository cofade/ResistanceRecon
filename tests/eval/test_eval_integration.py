"""End-to-end eval integration (EPIC 7 / issue #29), mirroring the predictor PR-B e2e:
synthetic cohort -> train_and_register (real orchestration) -> PredictorRegistry.load ->
evaluate_registry. Asserts the three-granularity contract, the reproduction cross-check, and
no-leakage. Offline; no Docker, no network.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest
from train_predictor import train_and_register

from genome_firewall.eval import evaluate_registry
from genome_firewall.features.feature_matrix import assemble_feature_matrix
from genome_firewall.features.vocabulary import build_vocabulary
from genome_firewall.predictor.model_registry import STATUS_TRAINED, PredictorRegistry
from tests.predictor.conftest import SyntheticCohort

_TrainedRun = tuple[PredictorRegistry, pd.DataFrame, pd.DataFrame, pd.DataFrame, dict]


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


def _train(cohort: SyntheticCohort, models_dir: Path) -> _TrainedRun:
    vectors, labels, metadata = cohort
    schema = build_vocabulary(vectors, amrfinder_db_version="2026-05-15.1")
    matrix = assemble_feature_matrix(vectors, schema)
    vector_by_id = {v.genome_id: v for v in vectors}
    labels_df = _labels_frame(labels)
    train_and_register(
        matrix, schema, labels_df, metadata, vector_by_id, models_dir=models_dir, alpha=0.10
    )
    return PredictorRegistry.load(models_dir), matrix, labels_df, metadata, vector_by_id


@pytest.mark.integration
def test_eval_three_granularities_and_reproduction(
    synthetic_cohort: SyntheticCohort, tmp_path: Path
) -> None:
    registry, matrix, labels_df, metadata, vectors = _train(synthetic_cohort, tmp_path)
    report = evaluate_registry(
        registry, matrix, labels_df, metadata, vectors, models_dir=tmp_path, seed=0
    )

    genta = report.drugs["gentamicin"]
    # (a) overall, (b) per-ST group, (c) unseen-lineage holdout -- all present.
    assert genta.overall.metrics is not None
    assert isinstance(genta.overall.metrics.resistant_recall, float)  # headline metric present
    assert genta.per_group  # non-empty per-ST breakdown
    assert genta.unseen_lineage.holdout_group
    assert genta.split_sizes.n_test > 0

    # Reproduction cross-check passes at seed 0: split reproduced bit-for-bit + no vibes numbers.
    assert genta.reproducibility.committed_match is True
    assert genta.reproducibility.compared_sets
    assert genta.reproducibility.mismatched_sets == ()

    # A thin drug is an honest skip, never a crash.
    assert "ciprofloxacin" in report.skipped
    assert report.skipped["ciprofloxacin"].status != STATUS_TRAINED
    assert "ciprofloxacin" not in report.drugs

    # Null-safety: single-class slices report auroc None across every trained drug (no crash).
    for drug_eval in report.drugs.values():
        slices = (drug_eval.overall, *drug_eval.per_group, drug_eval.unseen_lineage.slice)
        for slc in slices:
            if slc.metrics is not None and slc.metrics.single_class:
                assert slc.metrics.auroc is None

    # Selective pair honest bounds.
    assert 0.0 <= genta.overall.selective.no_call_rate <= 1.0
    acc = genta.overall.selective.accuracy_on_called
    assert acc is None or 0.0 <= acc <= 1.0

    # Dataset fingerprint traces the exact inputs.
    assert report.dataset.n_genomes == matrix.shape[0]
    assert report.n_features == matrix.shape[1]


@pytest.mark.integration
def test_tampered_committed_metrics_trips_cross_check(
    synthetic_cohort: SyntheticCohort, tmp_path: Path
) -> None:
    registry, matrix, labels_df, metadata, vectors = _train(synthetic_cohort, tmp_path)
    # Corrupt the committed test_marginal on disk: a wrong assumed split (or any drift between
    # the persisted model and its committed metrics) makes the re-scored numbers disagree with
    # the committed artifact. The cross-check is the ONLY guard against a wrong-but-internally-
    # disjoint split -- no_leakage_check cannot see it -- so it must flag exactly this. (A clean
    # synthetic model scores identically on every fold, so a wrong *seed* alone need not diverge;
    # tampering isolates the guard deterministically.)
    metrics_path = tmp_path / "gentamicin" / "v1" / "metrics.json"
    committed = json.loads(metrics_path.read_text(encoding="utf-8"))
    committed["test_marginal"]["balanced_accuracy"] += 0.1  # a value the harness cannot reproduce
    metrics_path.write_text(json.dumps(committed), encoding="utf-8")

    report = evaluate_registry(
        registry, matrix, labels_df, metadata, vectors, models_dir=tmp_path, seed=0
    )
    genta = report.drugs["gentamicin"]
    assert genta.reproducibility.committed_match is False
    assert "test_marginal" in genta.reproducibility.mismatched_sets
    assert genta.reproducibility.max_abs_delta is not None
    assert genta.reproducibility.max_abs_delta >= 0.1 - 1e-9
