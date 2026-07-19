"""Held-out evaluation over a trained registry (EPIC 7 / issue #29).

Per drug: metrics on the *served* (gate-negative) population at the three ml-methodology.md
granularities -- overall / per-ST group / unseen-lineage holdout -- plus the reproduction
cross-check that guards against a wrong-split leak. Pure (no writes); ``scripts/run_eval.py``
is the only writer. Consumes the frozen ``predictor``/``features`` contracts; never modifies
them, never imports ``llm``.
"""

from __future__ import annotations

import hashlib
from collections import defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path

import numpy as np
import numpy.typing as npt
import pandas as pd

from genome_firewall.constants import DEFAULT_CONFORMAL_ALPHA
from genome_firewall.eval.metrics import (
    classification_metrics,
    reliability_bins,
    selective_prediction,
)
from genome_firewall.eval.schemas import (
    DatasetFingerprint,
    DrugEvalMetrics,
    DrugEvalSkip,
    EvalMetricSet,
    EvalReport,
    EvalSlice,
    ReproCheck,
    SplitSizes,
    UnseenLineageEval,
)
from genome_firewall.eval.scoring import (
    EvalReproductionError,
    aligned_genome_ids,
    binary_labels_for,
    gate_positive_for,
    group_ids,
    reproduce_split,
    score_all,
)
from genome_firewall.predictor.conformal import ConformalArtifact
from genome_firewall.predictor.model_registry import (
    STATUS_TRAINED,
    DrugModel,
    PredictorRegistry,
    drug_slug,
)
from genome_firewall.predictor.split import (
    ClusterBackend,
    MlstStBackend,
    SplitResult,
    no_leakage_check,
)
from genome_firewall.predictor.train import DrugMetrics, MetricSet
from genome_firewall.schemas import GenomeFeatureVector

#: The committed metric sets (predictor.train.DrugMetrics) the cross-check re-derives.
_COMMITTED_SETS = (
    "test_marginal",
    "test_gate_negative",
    "holdout_marginal",
    "holdout_gate_negative",
)
#: The numeric fields shared by MetricSet and EvalMetricSet, compared bit-for-bit.
_CROSS_CHECK_FIELDS = (
    "balanced_accuracy",
    "resistant_recall",
    "susceptible_recall",
    "f1",
    "auroc",
    "pr_auc",
)
_CROSS_CHECK_ATOL = 1e-9


def _gate_negative(
    indices: Sequence[int], genome_ids: Sequence[str], gate_positive: Mapping[str, bool]
) -> list[int]:
    """Keep only positional indices whose genome does NOT fire the gate (the served set)."""
    return [i for i in indices if not gate_positive.get(genome_ids[i], False)]


def _slice(
    label: str,
    indices: Sequence[int],
    p_all: npt.NDArray[np.float64],
    y_int: Sequence[int],
    conformal: ConformalArtifact,
) -> EvalSlice:
    idx = list(indices)
    y_sub = [y_int[i] for i in idx]
    p_sub = p_all[idx]
    return EvalSlice(
        label=label,
        n=len(idx),
        metrics=classification_metrics(y_sub, p_sub),
        selective=selective_prediction(conformal, p_sub, y_sub),
        reliability=reliability_bins(y_sub, p_sub),
    )


def _compare_metric_sets(expected: MetricSet, got: EvalMetricSet) -> tuple[float, bool]:
    """Max abs delta over the shared numeric fields + whether they match within tolerance.
    A different fold size (n) is a structural mismatch: the wrong split was reproduced."""
    max_delta = 0.0
    ok = expected.n == got.n
    for field in _CROSS_CHECK_FIELDS:
        exp_val = getattr(expected, field)
        got_val = getattr(got, field)
        if exp_val is None and got_val is None:
            continue
        if exp_val is None or got_val is None:
            ok = False
            continue
        delta = abs(float(exp_val) - float(got_val))
        max_delta = max(max_delta, delta)
        if delta > _CROSS_CHECK_ATOL:
            ok = False
    return max_delta, ok


def _repro_check(
    committed: DrugMetrics | None,
    p_all: npt.NDArray[np.float64],
    y_int: Sequence[int],
    genome_ids: Sequence[str],
    gate_positive: Mapping[str, bool],
    split: SplitResult,
) -> ReproCheck:
    """Re-derive the four committed metric sets on the reproduced folds and compare to the
    committed ``metrics.json``. The wrong-but-valid-split leak (undetectable by
    ``no_leakage_check``) shows up here as a mismatch."""
    if committed is None:
        return ReproCheck(committed_match=None)
    assert split.split is not None and split.holdout is not None  # reproduce_split guaranteed it
    test_idx = list(split.split.test_index)
    holdout_idx = list(split.holdout.holdout_index)
    computed: dict[str, EvalMetricSet | None] = {
        "test_marginal": classification_metrics([y_int[i] for i in test_idx], p_all[test_idx]),
        "test_gate_negative": _subset_metrics(
            _gate_negative(test_idx, genome_ids, gate_positive), p_all, y_int
        ),
        "holdout_marginal": classification_metrics(
            [y_int[i] for i in holdout_idx], p_all[holdout_idx]
        ),
        "holdout_gate_negative": _subset_metrics(
            _gate_negative(holdout_idx, genome_ids, gate_positive), p_all, y_int
        ),
    }
    compared: list[str] = []
    mismatched: list[str] = []
    max_delta = 0.0
    for name in _COMMITTED_SETS:
        expected = getattr(committed, name)
        got = computed[name]
        if expected is None or got is None:
            continue
        compared.append(name)
        delta, ok = _compare_metric_sets(expected, got)
        max_delta = max(max_delta, delta)
        if not ok:
            mismatched.append(name)
    return ReproCheck(
        compared_sets=tuple(compared),
        mismatched_sets=tuple(mismatched),
        committed_match=(len(mismatched) == 0) if compared else None,
        max_abs_delta=max_delta if compared else None,
    )


def _subset_metrics(
    indices: Sequence[int], p_all: npt.NDArray[np.float64], y_int: Sequence[int]
) -> EvalMetricSet | None:
    idx = list(indices)
    return classification_metrics([y_int[i] for i in idx], p_all[idx])


def evaluate_drug(
    drug_model: DrugModel,
    committed: DrugMetrics | None,
    matrix: pd.DataFrame,
    labels_df: pd.DataFrame,
    metadata: pd.DataFrame,
    vectors: Mapping[str, GenomeFeatureVector],
    *,
    seed: int = 0,
    n_splits: int = 5,
    backend: ClusterBackend | None = None,
) -> DrugEvalMetrics:
    """Evaluate one trained drug: reproduce the split, re-score, cross-check, then report the
    served-population metrics at all three granularities."""
    antibiotic = drug_model.antibiotic
    labels_map = binary_labels_for(labels_df, antibiotic)
    genome_ids = aligned_genome_ids(matrix, labels_map)
    y = [labels_map[gid] for gid in genome_ids]
    y_int = [1 if side == "R" else 0 for side in y]
    split = reproduce_split(
        genome_ids,
        y,
        metadata,
        antibiotic=antibiotic,
        seed=seed,
        n_splits=n_splits,
        backend=backend,
    )
    assert split.split is not None and split.holdout is not None  # reproduce_split guaranteed it
    groups = group_ids(genome_ids, metadata, backend=backend)
    # Explicit P0 tripwire (make_split already checks internally): defence in depth documenting
    # that train/calibration/test/holdout are group-disjoint.
    no_leakage_check(
        groups,
        split.split.train_index,
        split.split.calibration_index,
        split.split.test_index,
        split.holdout.holdout_index,
    )
    p_all = score_all(drug_model, matrix, genome_ids)
    gate_positive = gate_positive_for(vectors, antibiotic)
    conformal = drug_model.conformal

    reproducibility = _repro_check(committed, p_all, y_int, genome_ids, gate_positive, split)

    served_test = _gate_negative(split.split.test_index, genome_ids, gate_positive)
    overall = _slice("overall", served_test, p_all, y_int, conformal)
    buckets: dict[str, list[int]] = defaultdict(list)
    for i in served_test:
        buckets[groups[i]].append(i)
    per_group = tuple(
        _slice(group, idxs, p_all, y_int, conformal) for group, idxs in sorted(buckets.items())
    )
    served_holdout = _gate_negative(split.holdout.holdout_index, genome_ids, gate_positive)
    unseen = UnseenLineageEval(
        holdout_group=split.holdout.holdout_group,
        slice=_slice(split.holdout.holdout_group, served_holdout, p_all, y_int, conformal),
    )
    return DrugEvalMetrics(
        antibiotic=antibiotic,
        model_version=drug_model.version,
        alpha=conformal.alpha,
        seed=seed,
        backend=split.backend,
        n_groups=split.n_groups,
        split_sizes=SplitSizes(
            n_train=len(split.split.train_index),
            n_calibration=len(split.split.calibration_index),
            n_test=len(split.split.test_index),
            n_holdout=len(split.holdout.holdout_index),
        ),
        overall=overall,
        per_group=per_group,
        unseen_lineage=unseen,
        reproducibility=reproducibility,
    )


def _load_committed_metrics(
    models_dir: str | Path, antibiotic: str, version: str
) -> DrugMetrics | None:
    path = Path(models_dir) / drug_slug(antibiotic) / version / "metrics.json"
    if not path.exists():
        return None
    return DrugMetrics.model_validate_json(path.read_text(encoding="utf-8"))


def evaluate_registry(
    registry: PredictorRegistry,
    matrix: pd.DataFrame,
    labels_df: pd.DataFrame,
    metadata: pd.DataFrame,
    vectors: Mapping[str, GenomeFeatureVector],
    *,
    models_dir: str | Path,
    alpha: float = DEFAULT_CONFORMAL_ALPHA,
    seed: int = 0,
    n_splits: int = 5,
    backend: ClusterBackend | None = None,
) -> EvalReport:
    """Evaluate every trained drug in ``registry``; insufficient-data or reproduction-failed
    drugs are recorded in ``skipped`` (never crash the whole run)."""
    drugs: dict[str, DrugEvalMetrics] = {}
    skipped: dict[str, DrugEvalSkip] = {}
    for antibiotic, entry in registry.entries.items():
        drug_model = registry.drugs.get(antibiotic)
        if entry.status != STATUS_TRAINED or drug_model is None:
            skipped[antibiotic] = DrugEvalSkip(
                antibiotic=antibiotic, status=entry.status, reason=entry.reason
            )
            continue
        committed = _load_committed_metrics(models_dir, antibiotic, drug_model.version)
        try:
            drugs[antibiotic] = evaluate_drug(
                drug_model,
                committed,
                matrix,
                labels_df,
                metadata,
                vectors,
                seed=seed,
                n_splits=n_splits,
                backend=backend,
            )
        except EvalReproductionError as exc:
            skipped[antibiotic] = DrugEvalSkip(
                antibiotic=antibiotic, status="reproduction_failed", reason=str(exc)
            )
    genome_index = sorted(str(gid) for gid in matrix.index)
    fingerprint = DatasetFingerprint(
        n_genomes=len(genome_index),
        n_features=len(matrix.columns),
        genome_ids_sha256=hashlib.sha256("\n".join(genome_index).encode("utf-8")).hexdigest(),
    )
    backend_name = backend.name if backend is not None else MlstStBackend().name
    return EvalReport(
        alpha=alpha,
        seed=seed,
        backend=backend_name,
        amrfinder_db_version=registry.amrfinder_db_version,
        schema_version=registry.schema_version,
        n_features=len(matrix.columns),
        dataset=fingerprint,
        drugs=drugs,
        skipped=skipped,
    )
