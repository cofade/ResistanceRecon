"""Conformal LAC-Mondrian tests (issue #21): guarantee floor, verdict mapping, empirical
coverage, alpha-sensitivity, and the small-calibration unavailable flag. Offline, deterministic.
"""

from __future__ import annotations

import numpy as np

from genome_firewall.predictor.conformal import (
    ConformalArtifact,
    alpha_sensitivity,
    conformal_guarantee_available,
    evaluate_conformal,
    fit_conformal,
    mapie_lac_coverage,
    predict_set,
)
from genome_firewall.schemas import verdict_for_conformal_set


def _separated_probs(n: int, seed: int = 0) -> tuple[list[float], list[int]]:
    """A well-separated binary problem: R examples cluster near p=0.85, S near p=0.15."""
    rng = np.random.default_rng(seed)
    y = [1] * (n // 2) + [0] * (n - n // 2)
    p = [
        float(np.clip(rng.normal(0.85 if label == 1 else 0.15, 0.08), 0.001, 0.999)) for label in y
    ]
    return p, y


def test_guarantee_floor() -> None:
    # n >= ceil(1/alpha) - 1 per class.
    assert conformal_guarantee_available(9, 0.10) is True
    assert conformal_guarantee_available(8, 0.10) is False
    assert conformal_guarantee_available(19, 0.05) is True
    assert conformal_guarantee_available(18, 0.05) is False


def test_predict_set_verdict_mapping_is_exhaustive() -> None:
    # Construct artifacts directly so each of the four set shapes is exercised deterministically.
    tight = ConformalArtifact(
        alpha=0.1,
        tau_s=0.3,
        tau_r=0.3,
        n_cal_susceptible=50,
        n_cal_resistant=50,
        guarantee_available=True,
    )
    assert predict_set(tight, 0.1).labels == ("S",)  # p<=tau_s only
    assert verdict_for_conformal_set(predict_set(tight, 0.1).labels) == "likely_to_work"
    assert predict_set(tight, 0.9).labels == ("R",)  # (1-p)<=tau_r only
    assert verdict_for_conformal_set(predict_set(tight, 0.9).labels) == "likely_to_fail"
    assert predict_set(tight, 0.5).labels == ()  # neither admitted -> empty (novel/OOD)
    assert verdict_for_conformal_set(predict_set(tight, 0.5).labels) == "no_call"

    wide = ConformalArtifact(
        alpha=0.1,
        tau_s=0.6,
        tau_r=0.6,
        n_cal_susceptible=50,
        n_cal_resistant=50,
        guarantee_available=True,
    )
    assert set(predict_set(wide, 0.5).labels) == {"S", "R"}  # both admitted -> ambiguous
    assert verdict_for_conformal_set(predict_set(wide, 0.5).labels) == "no_call"


def test_empirical_coverage_meets_target() -> None:
    p_cal, y_cal = _separated_probs(400, seed=1)
    p_test, y_test = _separated_probs(400, seed=2)
    artifact = fit_conformal(p_cal, y_cal, alpha=0.10)
    assert artifact.guarantee_available is True
    evaluation = evaluate_conformal(artifact, p_test, y_test)
    # Class-conditional LAC targets >= 1 - alpha coverage; allow finite-sample slack.
    assert evaluation.coverage >= 0.85


def test_alpha_sensitivity_smaller_alpha_covers_more() -> None:
    p_cal, y_cal = _separated_probs(400, seed=3)
    p_test, y_test = _separated_probs(400, seed=4)
    # Grid descending so a smaller alpha (wider sets) should not cover less than a larger one.
    evals = alpha_sensitivity(p_cal, y_cal, p_test, y_test, alphas=(0.20, 0.10, 0.05))
    coverages = [ev.coverage for ev in evals]
    assert coverages[-1] >= coverages[0] - 1e-9


def test_small_calibration_marks_guarantee_unavailable() -> None:
    # 5 per class at alpha=0.05 is below the ceil(1/alpha)-1 = 19 floor.
    p = [0.9, 0.8, 0.85, 0.7, 0.95, 0.1, 0.2, 0.15, 0.3, 0.05]
    y = [1, 1, 1, 1, 1, 0, 0, 0, 0, 0]
    artifact = fit_conformal(p, y, alpha=0.05)
    assert artifact.guarantee_available is False


def test_mapie_cross_check_returns_a_coverage() -> None:
    p_cal, y_cal = _separated_probs(200, seed=5)
    p_test, y_test = _separated_probs(200, seed=6)
    coverage = mapie_lac_coverage(p_cal, y_cal, p_test, y_test, alpha=0.10)
    assert coverage is not None
    assert 0.0 <= coverage <= 1.0
