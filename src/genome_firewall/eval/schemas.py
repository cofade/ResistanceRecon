"""Eval-local Pydantic schemas for the held-out evaluation report (EPIC 7 / issue #29).

These types are an internal *reporting* concern consumed by nobody downstream (only
``scripts/run_eval.py`` serializes them and the model card reads them), so they live here
rather than in the frozen cross-module ``genome_firewall.schemas`` -- the same reason
``predictor.conformal`` keeps ``ConformalArtifact``/``ConformalEval`` module-local.

Every metric is reproducible from a committed artifact or the harness (golden rule #3 -- no
vibes numbers): each nullable leaf maps to a *documented* undefined case (empty fold,
single-class fold, empty reliability bin, all-no-call slice), never to a fabricated value.
There is deliberately no wall-clock field, so a regenerated ``eval_summary.json`` is
byte-diffable against the committed one. LLM-free.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class _EvalModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class EvalMetricSet(_EvalModel):
    """Point-classification metrics on one slice.

    The six shared fields mirror ``predictor.train._metric_set`` exactly (0.5 threshold on
    P(resistant), same sklearn calls and ``zero_division=0``) so the runner's reproduction
    cross-check against the committed ``metrics.json`` is bit-exact. ``single_class`` flags a
    fold carrying only R or only S -- there the absent class's recall reads ``0.0`` and AUROC
    is ``None`` (undefined), so a ``0.0`` is never mistaken for a real score.
    """

    n: int
    n_resistant: int
    n_susceptible: int
    single_class: bool
    balanced_accuracy: float
    resistant_recall: float
    susceptible_recall: float
    f1: float
    auroc: float | None = None
    pr_auc: float | None = None
    brier: float | None = None


class ReliabilityBin(_EvalModel):
    """One uniform [0, 1] reliability bin. ``mean_predicted``/``fraction_positive`` are ``None``
    for an empty bin (count == 0). Bin counts sum to the slice's n (reproducible, not sampled)."""

    bin_lower: float
    bin_upper: float
    count: int
    mean_predicted: float | None = None
    fraction_positive: float | None = None


class SelectivePrediction(_EvalModel):
    """The selective-prediction pair (ml-methodology.md): conformal no-call behaviour plus
    accuracy-on-called. ``accuracy_on_called`` is ``None`` when nothing is called (an empty
    fold, or an all-no-call slice) -- never coerced to a meaningless number."""

    n: int
    n_called: int
    coverage: float
    no_call_rate: float
    empty_rate: float
    ambiguous_rate: float
    accuracy_on_called: float | None = None


class EvalSlice(_EvalModel):
    """The full metric bundle at one granularity. ``label`` is ``"overall"``, an ST group id,
    or the unseen-lineage holdout group. ``metrics`` is ``None`` on an empty slice."""

    label: str
    n: int
    metrics: EvalMetricSet | None = None
    selective: SelectivePrediction
    reliability: tuple[ReliabilityBin, ...] = ()


class UnseenLineageEval(_EvalModel):
    """Granularity (c): the entire held-out homology group the model never saw in training --
    the honest generalization signal (ADR-0005)."""

    holdout_group: str
    slice: EvalSlice


class SplitSizes(_EvalModel):
    n_train: int
    n_calibration: int
    n_test: int
    n_holdout: int


class ReproCheck(_EvalModel):
    """The anti-leakage tripwire.

    The harness re-derives the committed metric sets on the reproduced split and compares them
    to ``models/<drug>/v1/metrics.json``. A wrong assumed seed yields a *different-but-
    internally-disjoint* split (which ``no_leakage_check`` happily passes) whose test fold
    overlaps the model's real training genomes -- only this cross-check catches it. It also is
    the "no vibes numbers" guarantee: the reported metrics equal a committed artifact.
    ``committed_match`` is ``None`` when no committed ``metrics.json`` was available to compare.
    """

    compared_sets: tuple[str, ...] = ()
    mismatched_sets: tuple[str, ...] = ()
    committed_match: bool | None = None
    max_abs_delta: float | None = None


class DrugEvalMetrics(_EvalModel):
    """One trained drug's evaluation: metrics on the served (gate-negative) population at the
    three ml-methodology.md granularities plus the reproduction cross-check.

    ``seed``/``backend`` are the assumed training defaults -- they are NOT persisted with the
    model, so ``reproducibility`` is what validates the assumption held.
    """

    antibiotic: str
    model_version: str
    alpha: float
    seed: int
    backend: str
    n_groups: int
    population: Literal["gate_negative"] = "gate_negative"
    split_sizes: SplitSizes
    overall: EvalSlice
    per_group: tuple[EvalSlice, ...] = ()
    unseen_lineage: UnseenLineageEval
    reproducibility: ReproCheck


class DrugEvalSkip(_EvalModel):
    """A drug with no evaluable model: ``insufficient_data`` (per the registry) or a
    ``reproduction_failed`` surfaced honestly rather than crashing the whole run."""

    antibiotic: str
    status: str
    reason: str | None = None


class DatasetFingerprint(_EvalModel):
    """Exactly what was scored, so a committed report is traceable to its inputs."""

    n_genomes: int
    n_features: int
    genome_ids_sha256: str


class EvalReport(_EvalModel):
    """Top-level held-out evaluation over a trained registry -- serialized to
    ``models/eval_summary.json`` (committed ground-truth alongside ``results_summary.json``)."""

    eval_schema: Literal["genome-firewall-eval/1"] = "genome-firewall-eval/1"
    alpha: float
    seed: int
    backend: str
    amrfinder_db_version: str | None = None
    schema_version: str | None = None
    n_features: int
    dataset: DatasetFingerprint
    drugs: dict[str, DrugEvalMetrics] = Field(default_factory=dict)
    skipped: dict[str, DrugEvalSkip] = Field(default_factory=dict)
