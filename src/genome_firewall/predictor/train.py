"""Per-antibiotic L2 logistic regression + sigmoid calibration (issue #20, ADR-0003/0004).

One independent binary classifier per drug:
``LogisticRegression(penalty='l2', class_weight='balanced', solver='lbfgs', max_iter=2000)``
with C chosen by an inner homology-grouped CV grid search (PR-AUC scoring -- minority-aware).
L2 (not L1) because AMR genes co-occur on plasmids/operons and L1 arbitrarily zeroes
correlated markers.

**Trains on all labelled rows but reports headline metrics on the gate-negative subset**
(decision recorded in this epic's plan): the deterministic gate short-circuits gate-positive
genomes at inference, so the population the model actually serves is the gate-negative one.
Drugs failing the min-n gate get status='insufficient_data' and no model. Pure sklearn;
LLM-free (no import of genome_firewall.llm).
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import numpy.typing as npt
import pandas as pd
from pydantic import BaseModel, ConfigDict
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    average_precision_score,
    balanced_accuracy_score,
    f1_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import GridSearchCV, StratifiedGroupKFold

from genome_firewall.predictor.calibration import (
    CalibrationReport,
    calibrate,
    calibration_report,
    predict_resistant_proba,
)
from genome_firewall.predictor.split import (
    MinNGateResult,
    MlstStBackend,
    SplitResult,
    make_split,
    safe_n_splits,
)
from genome_firewall.schemas import ModelFeatureSchema


class _Frozen(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class TrainingConfig(_Frozen):
    """Hyperparameters + split controls for one training run (ADR-0003/0004)."""

    seed: int = 0
    c_grid: tuple[float, ...] = (0.01, 0.1, 1.0, 10.0, 100.0)
    n_splits: int = 5
    calibration_method: str = "sigmoid"
    top_k_coefficients: int = 20


DEFAULT_TRAINING_CONFIG = TrainingConfig()


class MetricSet(_Frozen):
    """Classification metrics on one evaluation subset (challenge-brief success criteria)."""

    n: int
    n_resistant: int
    n_susceptible: int
    balanced_accuracy: float
    resistant_recall: float
    susceptible_recall: float
    f1: float
    auroc: float | None = None
    pr_auc: float | None = None


class DrugMetrics(_Frozen):
    """Marginal + gate-negative metrics on the grouped test fold and the unseen-lineage
    holdout. The gate-negative sets are the headline (the population the model serves)."""

    test_marginal: MetricSet | None = None
    test_gate_negative: MetricSet | None = None
    holdout_marginal: MetricSet | None = None
    holdout_gate_negative: MetricSet | None = None


class SignedCoefficient(_Frozen):
    """One L2-LR coefficient (the model's own weight) -- statistical-association evidence."""

    feature: str
    coefficient: float


@dataclass
class DrugTrainingResult:
    """Everything one drug's training produced. Carries live sklearn objects (persisted via
    joblib by the PR-B registry) plus the serializable metric/calibration/coefficient records.
    """

    antibiotic: str
    status: str  # "trained" | "insufficient_data"
    min_n: MinNGateResult
    split: SplitResult
    model_version: str | None = None
    feature_schema: ModelFeatureSchema | None = None
    uncalibrated_model: Any = None
    calibrated_model: Any = None
    best_c: float | None = None
    metrics: DrugMetrics | None = None
    calibration: CalibrationReport | None = None
    coefficients: tuple[SignedCoefficient, ...] = field(default_factory=tuple)


def _slug(antibiotic: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", antibiotic.lower()).strip("-")


def _metric_set(y_true: Sequence[int], proba: npt.NDArray[np.float64]) -> MetricSet | None:
    y = np.asarray(y_true, dtype=int)
    if y.size == 0:
        return None
    pred = (proba >= 0.5).astype(int)
    n_r = int(y.sum())
    n_s = int(y.size) - n_r
    both = n_r > 0 and n_s > 0
    return MetricSet(
        n=int(y.size),
        n_resistant=n_r,
        n_susceptible=n_s,
        balanced_accuracy=(
            float(balanced_accuracy_score(y, pred)) if both else float((pred == y).mean())
        ),
        resistant_recall=float(recall_score(y, pred, pos_label=1, zero_division=0)),
        susceptible_recall=float(recall_score(y, pred, pos_label=0, zero_division=0)),
        f1=float(f1_score(y, pred, pos_label=1, zero_division=0)),
        auroc=float(roc_auc_score(y, proba)) if both else None,
        pr_auc=float(average_precision_score(y, proba)) if n_r > 0 else None,
    )


def _evaluate_subset(
    calibrated: Any,
    x: npt.NDArray[np.float64],
    y_int: Sequence[int],
    genome_ids: Sequence[str],
    index: Sequence[int],
    gate_positive: Mapping[str, bool] | None,
) -> tuple[MetricSet | None, MetricSet | None]:
    subset = list(index)
    if not subset:
        return None, None
    proba = predict_resistant_proba(calibrated, x[subset])
    y_sub = [y_int[i] for i in subset]
    marginal = _metric_set(y_sub, proba)
    if gate_positive is None:
        return marginal, None
    keep = [j for j, i in enumerate(subset) if not gate_positive.get(genome_ids[i], False)]
    if not keep or len(keep) == len(subset):
        # No gate-positive rows here -> gate-negative == marginal; avoid a redundant copy.
        return marginal, marginal if len(keep) == len(subset) else None
    gate_negative = _metric_set([y_sub[j] for j in keep], proba[keep])
    return marginal, gate_negative


def _top_coefficients(
    model: Any, feature_names: Sequence[str], top_k: int
) -> tuple[SignedCoefficient, ...]:
    weights = np.asarray(model.coef_, dtype=float).ravel()
    pairs = [
        SignedCoefficient(feature=name, coefficient=float(weight))
        for name, weight in zip(feature_names, weights, strict=True)
    ]
    pairs.sort(key=lambda c: (-abs(c.coefficient), c.feature))
    return tuple(pairs[:top_k])


def train_one_antibiotic(
    feature_matrix: pd.DataFrame,
    labels: Mapping[str, str],
    metadata: pd.DataFrame,
    *,
    antibiotic: str,
    feature_schema: ModelFeatureSchema,
    config: TrainingConfig = DEFAULT_TRAINING_CONFIG,
    gate_positive: Mapping[str, bool] | None = None,
) -> DrugTrainingResult:
    """Train + calibrate one drug's model. ``labels`` maps genome_id -> "R"/"S" (already
    binary-collapsed). ``gate_positive`` (genome_id -> fired) enables the gate-negative
    headline metrics; omit it to report marginal metrics only.
    """
    genome_ids = sorted(set(feature_matrix.index) & set(labels))
    y = [labels[gid] for gid in genome_ids]
    y_int = [1 if label == "R" else 0 for label in y]

    split = make_split(
        genome_ids, y, metadata, antibiotic=antibiotic, n_splits=config.n_splits, seed=config.seed
    )
    if not split.min_n.ok or split.split is None or split.holdout is None:
        return DrugTrainingResult(
            antibiotic=antibiotic, status="insufficient_data", min_n=split.min_n, split=split
        )

    x = feature_matrix.loc[genome_ids].to_numpy(dtype=np.float64)
    group_map = MlstStBackend().assign_groups(genome_ids, metadata)
    groups = [group_map[gid] for gid in genome_ids]

    train_idx = list(split.split.train_index)
    x_train = x[train_idx]
    y_train = [y_int[i] for i in train_idx]
    groups_train = [groups[i] for i in train_idx]

    # L2 is LogisticRegression's default penalty (ADR-0003 wants L2); passing penalty='l2'
    # explicitly is deprecated in sklearn>=1.8 and removed in 1.10, so we rely on the default
    # to keep the same L2 regularization warning-free and forward-compatible.
    base = LogisticRegression(class_weight="balanced", solver="lbfgs", max_iter=2000)
    k = safe_n_splits(y_train, groups_train, config.n_splits)
    grid = GridSearchCV(
        base,
        {"C": list(config.c_grid)},
        cv=StratifiedGroupKFold(n_splits=k, shuffle=True, random_state=config.seed),
        scoring="average_precision",
        n_jobs=1,
    )
    grid.fit(x_train, y_train, groups=groups_train)
    best_model = grid.best_estimator_
    best_c = float(grid.best_params_["C"])

    cal_idx = list(split.split.calibration_index)
    calibrated = calibrate(
        best_model, x[cal_idx], [y_int[i] for i in cal_idx], method=config.calibration_method
    )
    calibration = calibration_report(calibrated, x[cal_idx], [y_int[i] for i in cal_idx])

    test_marginal, test_gate_negative = _evaluate_subset(
        calibrated, x, y_int, genome_ids, split.split.test_index, gate_positive
    )
    holdout_marginal, holdout_gate_negative = _evaluate_subset(
        calibrated, x, y_int, genome_ids, split.holdout.holdout_index, gate_positive
    )

    return DrugTrainingResult(
        antibiotic=antibiotic,
        status="trained",
        min_n=split.min_n,
        split=split,
        model_version=f"lr-{_slug(antibiotic)}-{feature_schema.vocabulary_sha256[:8]}",
        feature_schema=feature_schema,
        uncalibrated_model=best_model,
        calibrated_model=calibrated,
        best_c=best_c,
        metrics=DrugMetrics(
            test_marginal=test_marginal,
            test_gate_negative=test_gate_negative,
            holdout_marginal=holdout_marginal,
            holdout_gate_negative=holdout_gate_negative,
        ),
        calibration=calibration,
        coefficients=_top_coefficients(
            best_model, feature_schema.feature_names, config.top_k_coefficients
        ),
    )
