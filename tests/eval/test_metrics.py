"""Unit tests for the pure eval metrics (EPIC 7 / issue #29). Fast, no I/O, no marker.

The headline test is *frozen-producer parity*: ``classification_metrics`` must equal
``predictor.train._metric_set`` field-for-field, so the runner's reproduction cross-check is
meaningful. The rest pin the documented edge cases (single-class, empty fold, all-no-call).
"""

from __future__ import annotations

import numpy as np
import pytest

from genome_firewall.eval.metrics import (
    accuracy_on_called,
    classification_metrics,
    reliability_bins,
    selective_prediction,
)
from genome_firewall.predictor.conformal import ConformalArtifact
from genome_firewall.predictor.train import _metric_set

_SHARED_FIELDS = (
    "balanced_accuracy",
    "resistant_recall",
    "susceptible_recall",
    "f1",
    "auroc",
    "pr_auc",
)


def _artifact(tau_s: float, tau_r: float) -> ConformalArtifact:
    return ConformalArtifact(
        alpha=0.1,
        tau_s=tau_s,
        tau_r=tau_r,
        n_cal_susceptible=10,
        n_cal_resistant=10,
        guarantee_available=True,
    )


def test_classification_metrics_matches_frozen_metric_set() -> None:
    rng = np.random.default_rng(0)
    y = rng.integers(0, 2, size=40).tolist()
    y[0], y[1] = 0, 1  # guarantee both classes present
    proba = rng.random(40)
    got = classification_metrics(y, proba)
    expected = _metric_set(y, proba)
    assert got is not None and expected is not None
    for field in _SHARED_FIELDS:
        assert getattr(got, field) == pytest.approx(getattr(expected, field))
    assert (got.n, got.n_resistant, got.n_susceptible) == (
        expected.n,
        expected.n_resistant,
        expected.n_susceptible,
    )
    assert got.brier is not None  # net-new field beyond the frozen producer


def test_classification_metrics_empty_fold_is_none() -> None:
    assert classification_metrics([], np.array([], dtype=float)) is None


def test_classification_metrics_single_class_resistant() -> None:
    got = classification_metrics([1, 1, 1], np.array([0.9, 0.8, 0.6]))
    assert got is not None
    assert got.single_class is True
    assert got.auroc is None  # AUROC undefined without both classes
    assert got.susceptible_recall == 0.0  # absent class -> zero_division=0, not a real score


def test_classification_metrics_single_class_susceptible_has_no_pr_auc() -> None:
    got = classification_metrics([0, 0, 0], np.array([0.1, 0.2, 0.3]))
    assert got is not None
    assert got.single_class is True
    assert got.auroc is None
    assert got.pr_auc is None  # no positive -> average precision undefined


def test_reliability_bins_counts_sum_to_n() -> None:
    y = [0, 1, 0, 1, 1]
    proba = np.array([0.05, 0.95, 0.15, 0.85, 0.55])
    bins = reliability_bins(y, proba, n_bins=10)
    assert sum(b.count for b in bins) == len(y)
    assert reliability_bins([], np.array([], dtype=float)) == ()


def test_accuracy_on_called_all_correct_singletons() -> None:
    # true-S (low p) and true-R (high p); tau_s == tau_r == 0.5 -> each gets its own singleton.
    sel = selective_prediction(_artifact(0.5, 0.5), [0.1, 0.9, 0.2, 0.8], [0, 1, 0, 1])
    assert sel.n_called == 4
    assert sel.accuracy_on_called == pytest.approx(1.0)
    assert sel.no_call_rate == pytest.approx(0.0)


def test_selective_all_no_call_returns_none_accuracy() -> None:
    # tau_s == tau_r == 0.0 -> nothing is ever included -> every set empty -> all-no-call.
    sel = selective_prediction(_artifact(0.0, 0.0), [0.2, 0.5, 0.8], [0, 1, 1])
    assert sel.n_called == 0
    assert sel.accuracy_on_called is None
    assert sel.no_call_rate == pytest.approx(1.0)
    assert sel.empty_rate == pytest.approx(1.0)


def test_accuracy_on_called_empty_is_zero_none() -> None:
    assert accuracy_on_called([], []) == (0, None)
