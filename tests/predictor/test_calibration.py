"""Tests for sigmoid calibration on a prefit model (issue #20, ADR-0004)."""

from __future__ import annotations

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
