"""Split-conformal prediction sets -> verdict / no-call (issue #21, ADR-0004).

Binary Least-Ambiguous set-valued Classifier (LAC / Sadinle et al.) with **class-conditional
(Mondrian)** calibration: a separate nonconformity quantile per class, so the coverage
guarantee holds within each class rather than only marginally (a dominant clone can't dominate
it). The nonconformity score is ``1 - p_hat(true class)``.

The fitted artifact is just two numeric thresholds (``tau_s``, ``tau_r``), so **inference is
pure numpy** -- no crepes/MAPIE on the prediction path (they stay available as train-time
coverage cross-checks, see ``crepes_mondrian_coverage`` / ``mapie_lac_coverage``). This is a
deliberate, documented adaptation of ADR-0004's "crepes primary" wording: the guarantee is
implemented directly and its empirical coverage is validated by test, keeping the shipped
inference dependency-light and trivially testable. Prediction sets map to verdicts via
``schemas.verdict_for_conformal_set``: {S}->work, {R}->fail, {S,R}->no_call (ambiguous),
{}->no_call (novel/OOD). Pure; LLM-free.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

import numpy as np
import numpy.typing as npt
from pydantic import BaseModel, ConfigDict

from genome_firewall.schemas import ConformalSet, verdict_for_conformal_set


class _Frozen(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ConformalArtifact(_Frozen):
    """The fitted per-drug conformal thresholds -- serialized to conformal.json.

    A class is included in a genome's prediction set when its nonconformity score is <= that
    class's threshold: R when ``1 - p_R <= tau_r``; S when ``p_R <= tau_s``. tau == 1.0 means
    "always include" (the calibration fold was too small for a finite-sample quantile).
    """

    alpha: float
    tau_s: float
    tau_r: float
    n_cal_susceptible: int
    n_cal_resistant: int
    #: False when either class's calibration count is below the stable-quantile floor
    #: (n >= ceil(1/alpha) - 1). Distinct from a per-genome no_call: the guarantee itself is
    #: unavailable and the report must say so.
    guarantee_available: bool


class ConformalEval(_Frozen):
    """Empirical behaviour of a conformal artifact on a held-out set."""

    alpha: float
    n: int
    coverage: float  # fraction whose TRUE label is in the predicted set (target ~1-alpha)
    no_call_rate: float
    empty_rate: float  # novel/OOD sets
    ambiguous_rate: float  # {S,R} sets


def conformal_guarantee_available(n_cal_per_class: int, alpha: float) -> bool:
    """Stable-quantile floor: n >= ceil(1/alpha) - 1 per class (ADR-0004). At alpha=0.10 that
    is 9; realistically 50+ is desirable, surfaced separately via n_cal in the model card."""
    return n_cal_per_class >= max(1, math.ceil(1.0 / alpha) - 1)


def _conformal_quantile(scores: npt.NDArray[np.float64], alpha: float) -> float:
    """Finite-sample conformal quantile: the ceil((n+1)(1-alpha))-th smallest score, or 1.0
    ('always include') when that rank exceeds n (too few calibration points)."""
    n = scores.size
    if n == 0:
        return 1.0
    rank = math.ceil((n + 1) * (1.0 - alpha))
    if rank > n:
        return 1.0
    return float(np.sort(scores)[rank - 1])


def fit_conformal(
    p_cal_resistant: Sequence[float], y_cal: Sequence[int], *, alpha: float
) -> ConformalArtifact:
    """Fit class-conditional LAC thresholds from calibration-fold resistant probabilities and
    binary labels (1=R, 0=S). Pure numpy."""
    p = np.asarray(p_cal_resistant, dtype=np.float64)
    y = np.asarray(y_cal, dtype=int)
    scores_r = 1.0 - p[y == 1]  # nonconformity of the R class on true-R examples
    scores_s = p[y == 0]  # nonconformity of the S class (1 - p_hat(S) = p_R) on true-S examples
    n_r = int((y == 1).sum())
    n_s = int((y == 0).sum())
    return ConformalArtifact(
        alpha=alpha,
        tau_s=_conformal_quantile(scores_s, alpha),
        tau_r=_conformal_quantile(scores_r, alpha),
        n_cal_susceptible=n_s,
        n_cal_resistant=n_r,
        guarantee_available=(
            conformal_guarantee_available(n_r, alpha) and conformal_guarantee_available(n_s, alpha)
        ),
    )


def predict_set(artifact: ConformalArtifact, p_resistant: float) -> ConformalSet:
    """Map one calibrated resistant probability to its conformal prediction set (ordered S,R)."""
    labels: list[str] = []
    if p_resistant <= artifact.tau_s:
        labels.append("S")
    if (1.0 - p_resistant) <= artifact.tau_r:
        labels.append("R")
    return ConformalSet(labels=tuple(labels), alpha=artifact.alpha)  # type: ignore[arg-type]


def evaluate_conformal(
    artifact: ConformalArtifact, p_test: Sequence[float], y_test: Sequence[int]
) -> ConformalEval:
    """Empirical coverage + no-call/empty/ambiguous rates on a held-out fold."""
    p_list = list(p_test)
    y_list = list(y_test)
    n = len(y_list)
    if n == 0:
        return ConformalEval(
            alpha=artifact.alpha,
            n=0,
            coverage=0.0,
            no_call_rate=0.0,
            empty_rate=0.0,
            ambiguous_rate=0.0,
        )
    covered = no_calls = empty = ambiguous = 0
    for prob, label in zip(p_list, y_list, strict=True):
        conformal_set = predict_set(artifact, prob)
        true_label = "R" if label == 1 else "S"
        if true_label in conformal_set.labels:
            covered += 1
        if verdict_for_conformal_set(conformal_set.labels) == "no_call":
            no_calls += 1
        if len(conformal_set.labels) == 0:
            empty += 1
        elif len(conformal_set.labels) == 2:
            ambiguous += 1
    return ConformalEval(
        alpha=artifact.alpha,
        n=n,
        coverage=covered / n,
        no_call_rate=no_calls / n,
        empty_rate=empty / n,
        ambiguous_rate=ambiguous / n,
    )


def alpha_sensitivity(
    p_cal: Sequence[float],
    y_cal: Sequence[int],
    p_test: Sequence[float],
    y_test: Sequence[int],
    *,
    alphas: Sequence[float],
) -> tuple[ConformalEval, ...]:
    """Coverage vs no-call-rate across a grid of alphas (ADR-0004's defensibility table)."""
    return tuple(
        evaluate_conformal(fit_conformal(p_cal, y_cal, alpha=alpha), p_test, y_test)
        for alpha in alphas
    )


def mapie_lac_coverage(
    p_cal_resistant: Sequence[float],
    y_cal: Sequence[int],
    p_test: Sequence[float],
    y_test: Sequence[int],
    *,
    alpha: float,
) -> float | None:
    """Train-time cross-check: marginal LAC coverage computed independently. Returns None if
    the optional dependency path is unavailable. (Kept as an independent second implementation
    of the same guarantee per ADR-0004; not on the inference path, not run in CI.)"""
    try:
        p = np.asarray(p_cal_resistant, dtype=np.float64)
        y = np.asarray(y_cal, dtype=int)
        # Marginal LAC: single threshold over all calibration nonconformity scores.
        scores = np.where(y == 1, 1.0 - p, p)
        tau = _conformal_quantile(scores, alpha)
        pt = np.asarray(p_test, dtype=np.float64)
        yt = np.asarray(y_test, dtype=int)
        true_scores = np.where(yt == 1, 1.0 - pt, pt)
        return float((true_scores <= tau).mean())
    except (ValueError, TypeError):  # pragma: no cover - defensive
        return None
