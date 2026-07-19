"""Pure evaluation metrics (EPIC 7 / issue #29): no I/O, no model, no LLM.

The point-classification block mirrors ``predictor.train._metric_set`` field-for-field (same
sklearn calls, same ``zero_division=0``, same single-class fallbacks) so the runner's
reproduction cross-check against the committed ``metrics.json`` is exact. Brier, the uniform
reliability bins, and the selective-prediction pair (no-call rate + accuracy-on-called) are
the net-new honesty signals ml-methodology.md asks for beyond what training persisted.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
import numpy.typing as npt
from sklearn.metrics import (
    average_precision_score,
    balanced_accuracy_score,
    f1_score,
    recall_score,
    roc_auc_score,
)

from genome_firewall.eval.schemas import EvalMetricSet, ReliabilityBin, SelectivePrediction
from genome_firewall.predictor.conformal import ConformalArtifact, evaluate_conformal, predict_set


def classification_metrics(
    y_true: Sequence[int], proba: Sequence[float] | npt.NDArray[np.float64]
) -> EvalMetricSet | None:
    """The six ``_metric_set`` fields (0.5 threshold) plus Brier. ``None`` on an empty fold.

    Single-class folds keep the exact ``_metric_set`` fallbacks: plain accuracy for
    ``balanced_accuracy``, ``zero_division=0`` recalls/F1, ``auroc=None``, and ``pr_auc=None``
    when there is no positive. Brier is ``mean((proba - y)**2)`` -- unambiguous for a
    single-class fold (sklearn's ``brier_score_loss`` needs pos_label inference).
    """
    y = np.asarray(y_true, dtype=int)
    if y.size == 0:
        return None
    p = np.asarray(proba, dtype=np.float64)
    pred = (p >= 0.5).astype(int)
    n_r = int(y.sum())
    n_s = int(y.size) - n_r
    both = n_r > 0 and n_s > 0
    return EvalMetricSet(
        n=int(y.size),
        n_resistant=n_r,
        n_susceptible=n_s,
        single_class=not both,
        balanced_accuracy=(
            float(balanced_accuracy_score(y, pred)) if both else float((pred == y).mean())
        ),
        resistant_recall=float(recall_score(y, pred, pos_label=1, zero_division=0)),
        susceptible_recall=float(recall_score(y, pred, pos_label=0, zero_division=0)),
        f1=float(f1_score(y, pred, pos_label=1, zero_division=0)),
        auroc=float(roc_auc_score(y, p)) if both else None,
        pr_auc=float(average_precision_score(y, p)) if n_r > 0 else None,
        brier=float(np.mean((p - y) ** 2)),
    )


def reliability_bins(
    y_true: Sequence[int],
    proba: Sequence[float] | npt.NDArray[np.float64],
    *,
    n_bins: int = 10,
) -> tuple[ReliabilityBin, ...]:
    """Uniform [0, 1] calibration bins: per bin, count + mean predicted prob + observed
    fraction positive. Empty bins carry ``None`` for the two rates; counts sum to n. ``()`` on
    an empty fold."""
    y = np.asarray(y_true, dtype=np.float64)
    p = np.asarray(proba, dtype=np.float64)
    if y.size == 0:
        return ()
    edges = np.linspace(0.0, 1.0, n_bins + 1)
    # digitize on the interior edges, so p == 1.0 lands in the last bin, not an overflow bin.
    bin_index = np.clip(np.digitize(p, edges[1:-1], right=False), 0, n_bins - 1)
    bins: list[ReliabilityBin] = []
    for b in range(n_bins):
        mask = bin_index == b
        count = int(mask.sum())
        bins.append(
            ReliabilityBin(
                bin_lower=float(edges[b]),
                bin_upper=float(edges[b + 1]),
                count=count,
                mean_predicted=float(p[mask].mean()) if count else None,
                fraction_positive=float(y[mask].mean()) if count else None,
            )
        )
    return tuple(bins)


def accuracy_on_called(
    label_sets: Sequence[tuple[str, ...]], y_true: Sequence[int]
) -> tuple[int, float | None]:
    """'accuracy-on-called', defined precisely: *called* = a genome whose conformal set is a
    singleton ({S} or {R}); accuracy = fraction of called genomes whose singleton label is the
    true label. Returns ``(n_called, accuracy)``; ``(0, None)`` when nothing is called (empty
    fold, or every genome is empty/ambiguous i.e. all-no-call)."""
    called = [
        (labels[0], y) for labels, y in zip(label_sets, y_true, strict=True) if len(labels) == 1
    ]
    if not called:
        return 0, None
    correct = sum(1 for label, y in called if label == ("R" if y == 1 else "S"))
    return len(called), correct / len(called)


def selective_prediction(
    artifact: ConformalArtifact,
    proba: Sequence[float] | npt.NDArray[np.float64],
    y_true: Sequence[int],
) -> SelectivePrediction:
    """Conformal coverage / no-call / empty / ambiguous rates (via the frozen
    ``evaluate_conformal``) plus the accuracy-on-called pair."""
    probs = [float(v) for v in proba]
    ev = evaluate_conformal(artifact, probs, y_true)
    label_sets = [predict_set(artifact, v).labels for v in probs]
    n_called, accuracy = accuracy_on_called(label_sets, y_true)
    return SelectivePrediction(
        n=ev.n,
        n_called=n_called,
        coverage=ev.coverage,
        no_call_rate=ev.no_call_rate,
        empty_rate=ev.empty_rate,
        ambiguous_rate=ev.ambiguous_rate,
        accuracy_on_called=accuracy,
    )
