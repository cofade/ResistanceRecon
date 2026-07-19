"""Tests for sigmoid calibration on a prefit model (issue #20, ADR-0004)."""

from __future__ import annotations

import warnings

import numpy as np
from sklearn.linear_model import LogisticRegression

from genome_firewall.predictor.calibration import (
    calibrate,
    calibration_report,
    predict_resistant_proba,
)


def test_calibrate_yields_valid_probabilities_and_a_report() -> None:
    rng = np.random.RandomState(0)
    x = rng.rand(80, 3)
    y = (x[:, 0] > 0.5).astype(int).tolist()
    model = LogisticRegression().fit(x, y)

    calibrated = calibrate(model, x, y)
    proba = predict_resistant_proba(calibrated, x)
    assert proba.min() >= 0.0 and proba.max() <= 1.0
    assert list(calibrated.classes_) == [0, 1]  # positive class is 1 (resistant)

    report = calibration_report(calibrated, x, y, n_bins=5)
    assert 0.0 <= report.brier <= 1.0
    assert report.n == 80
    assert len(report.mean_predicted) == len(report.fraction_positive)


def test_calibrate_is_warning_free_on_an_imbalanced_fold() -> None:
    # An imbalanced per-drug calibration fold (minority 4 < sklearn's default 5-fold) must not
    # emit the "least populated class ... less than n_splits" UserWarning -- the cv is bounded
    # to the minority size, and predictions are fold-independent under FrozenEstimator.
    rng = np.random.RandomState(1)
    x = rng.rand(60, 3)
    y = [1] * 4 + [0] * 56
    model = LogisticRegression().fit(x, y)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        calibrated = calibrate(model, x, y)
    messages = [str(item.message) for item in caught]
    assert not any("n_splits" in m or "populated" in m for m in messages), messages
    assert 0.0 <= predict_resistant_proba(calibrated, x).max() <= 1.0


def test_calibrate_rejects_a_degenerate_minority_of_one() -> None:
    # A calibration fold with a single minority-class sample can't support any KFold; calibrate
    # raises a clear error (train_one_antibiotic gates on this upstream so it never fires there).
    import pytest

    rng = np.random.RandomState(2)
    x = rng.rand(20, 3)
    y = [1] + [0] * 19  # minority == 1
    model = LogisticRegression().fit(x, y)
    with pytest.raises(ValueError, match="minority class"):
        calibrate(model, x, y)
