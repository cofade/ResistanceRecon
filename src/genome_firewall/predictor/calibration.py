"""Sigmoid probability calibration on a homology-grouped fold (issue #20, ADR-0004).

``CalibratedClassifierCV(method='sigmoid')`` fitted on the grouped calibration fold with the
base model FROZEN, so only the 2-parameter Platt calibrator is learned -- the ``cv='prefit'``
intent of ADR-0004, expressed via scikit-learn>=1.6's ``FrozenEstimator`` (``cv='prefit'``
was deprecated in 1.6 and removed by 1.8; this project runs sklearn 1.9). Sigmoid, not
isotonic, because per-drug BV-BRC calibration folds rarely clear isotonic's ~1000-sample
floor and sigmoid is the recommended choice for imbalanced, under-confident classifiers.

The calibration fold is homology-grouped upstream (predictor/split.three_way_grouped_split)
so the calibrated probabilities are estimated on genomes group-disjoint from the training
set -- the outer boundary that matters. (Under FrozenEstimator the base model is not refit,
so the calibrator's own internal CV cannot leak clones; the internal CV's only job here is a
nominal split of the calibration fold, and its fold count is bounded to the minority-class
size below so it never emits sklearn's small-fold UserWarning.) Pure sklearn; LLM-free.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import numpy.typing as npt
from pydantic import BaseModel, ConfigDict
from sklearn.calibration import CalibratedClassifierCV, calibration_curve
from sklearn.metrics import brier_score_loss
from sklearn.model_selection import StratifiedKFold

try:  # sklearn >= 1.6
    from sklearn.frozen import FrozenEstimator

    _HAS_FROZEN = True
except ImportError:  # pragma: no cover - older sklearn fallback
    _HAS_FROZEN = False


class CalibrationReport(BaseModel):
    """Calibration quality on a held-out set: Brier score + reliability-curve points."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    brier: float
    n: int
    #: Reliability curve (sklearn.calibration.calibration_curve), non-empty bins only.
    mean_predicted: tuple[float, ...]
    fraction_positive: tuple[float, ...]


def calibrate(
    prefit_model: Any, x_cal: npt.NDArray[np.float64], y_cal: list[int], *, method: str = "sigmoid"
) -> Any:
    """Fit a sigmoid calibrator on the grouped calibration fold, keeping ``prefit_model``
    frozen (the ADR-0004 cv='prefit' semantics). Returns the fitted CalibratedClassifierCV.
    """
    if _HAS_FROZEN:
        # Bound the internal CV to the minority-class size so an imbalanced per-drug
        # calibration fold (e.g. a carbapenemase-heavy meropenem set) never triggers
        # sklearn's "least populated class has only N members < n_splits" UserWarning. Under
        # FrozenEstimator the base is not refit, so predictions are fold-independent and the
        # cv choice does not change the fitted calibrator -- only silences the warning.
        minority = min(y_cal.count(0), y_cal.count(1)) if y_cal else 0
        n_splits = max(2, min(5, minority))
        cv = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=0)
        calibrated = CalibratedClassifierCV(FrozenEstimator(prefit_model), method=method, cv=cv)
    else:  # pragma: no cover - older sklearn fallback
        calibrated = CalibratedClassifierCV(prefit_model, method=method, cv="prefit")
    calibrated.fit(x_cal, y_cal)
    return calibrated


def predict_resistant_proba(calibrated: Any, x: npt.NDArray[np.float64]) -> npt.NDArray[np.float64]:
    """P(resistant) = probability of the positive class (1) from a calibrated classifier."""
    positive_index = list(calibrated.classes_).index(1)
    proba = calibrated.predict_proba(x)[:, positive_index]
    return np.asarray(proba, dtype=np.float64)


def calibration_report(
    calibrated: Any, x_test: npt.NDArray[np.float64], y_test: list[int], *, n_bins: int = 10
) -> CalibrationReport:
    """Brier score + reliability curve for a calibrated classifier on a held-out set."""
    proba = predict_resistant_proba(calibrated, x_test)
    brier = float(brier_score_loss(y_test, proba))
    fraction_positive, mean_predicted = calibration_curve(
        y_test, proba, n_bins=n_bins, strategy="uniform"
    )
    return CalibrationReport(
        brier=brier,
        n=len(y_test),
        mean_predicted=tuple(float(v) for v in mean_predicted),
        fraction_positive=tuple(float(v) for v in fraction_positive),
    )
