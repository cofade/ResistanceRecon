"""Split reproduction + re-scoring the persisted model on held-out folds (EPIC 7 / issue #29).

The harness re-scores the committed ``.joblib`` model on the SAME homology-grouped folds
training used. Correctness rests on reproducing training's split bit-for-bit: the identical
genome-id ordering (``sorted(set(matrix.index) & set(labels))``), identical binary labels (the
same ``predictor.dataset`` SIR-collapse primitives), and the training defaults ``seed=0`` /
``n_splits=5`` / ``MlstStBackend`` -- which are NOT persisted with the model, so the runner's
cross-check against the committed ``metrics.json`` is what validates the assumption. Splitting
is never re-implemented; ``predictor.split.make_split`` is reused verbatim. Pure; LLM-free.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

import numpy as np
import numpy.typing as npt
import pandas as pd

from genome_firewall.predictor.calibration import predict_resistant_proba
from genome_firewall.predictor.dataset import canonicalize_antibiotic, collapse_sir_to_binary
from genome_firewall.predictor.model_registry import DrugModel
from genome_firewall.predictor.split import (
    ClusterBackend,
    MlstStBackend,
    SplitResult,
    make_split,
)
from genome_firewall.predictor.target_gate import evaluate_gate
from genome_firewall.schemas import GenomeFeatureVector


class EvalReproductionError(RuntimeError):
    """A trained drug's homology split could not be reproduced. A trained model has a split by
    construction, so this signals dataset drift between training and evaluation (not a thin
    drug -- those never train)."""


def aligned_genome_ids(matrix: pd.DataFrame, labels_map: Mapping[str, str]) -> list[str]:
    """The EXACT ordering training's positional split indices index into
    (``predictor.train.train_one_antibiotic``); any other ordering silently mismaps folds."""
    return sorted(set(matrix.index) & set(labels_map))


def binary_labels_for(labels_df: pd.DataFrame, antibiotic: str) -> dict[str, str]:
    """genome_id -> 'R'/'S' for one drug, byte-identical to
    ``scripts.train_predictor.binary_labels_for`` (the same ``predictor.dataset`` primitives),
    so the reproduced labels match training exactly."""
    canonical = canonicalize_antibiotic(antibiotic)
    drug_rows = labels_df[labels_df["antibiotic"].map(canonicalize_antibiotic) == canonical]
    binary = collapse_sir_to_binary(drug_rows)
    return {
        str(gid): side for gid, side in zip(binary["genome_id"], binary["sir_binary"], strict=True)
    }


def gate_positive_for(
    vectors: Mapping[str, GenomeFeatureVector], antibiotic: str
) -> dict[str, bool]:
    """genome_id -> whether the deterministic gate fires. Defines the gate-negative *served*
    population -- the one the calibrated model actually decides, matching predictor.train's
    headline metrics."""
    return {gid: evaluate_gate(antibiotic, vector).result.fired for gid, vector in vectors.items()}


def group_ids(
    genome_ids: Sequence[str], metadata: pd.DataFrame, *, backend: ClusterBackend | None = None
) -> list[str]:
    """Homology-group id per genome, in ``genome_ids`` order, via the same backend the split
    uses (defaults to ``MlstStBackend``)."""
    resolved = backend if backend is not None else MlstStBackend()
    group_map = resolved.assign_groups(genome_ids, metadata)
    return [group_map[gid] for gid in genome_ids]


def reproduce_split(
    genome_ids: Sequence[str],
    y: Sequence[str],
    metadata: pd.DataFrame,
    *,
    antibiotic: str,
    seed: int = 0,
    n_splits: int = 5,
    backend: ClusterBackend | None = None,
) -> SplitResult:
    """Reproduce training's homology split (``make_split`` verbatim). Raises
    ``EvalReproductionError`` if a trained drug does not yield a split -- a divergence, since a
    trained model always had one."""
    split = make_split(
        genome_ids,
        y,
        metadata,
        antibiotic=antibiotic,
        backend=backend,
        n_splits=n_splits,
        seed=seed,
    )
    if split.split is None or split.holdout is None:
        raise EvalReproductionError(
            f"{antibiotic}: reproduced split is insufficient ({split.reason})"
        )
    return split


def score_all(
    drug_model: DrugModel, matrix: pd.DataFrame, genome_ids: Sequence[str]
) -> npt.NDArray[np.float64]:
    """Calibrated P(resistant) for every genome, aligned to ``genome_ids``.

    Reuses ``predict_resistant_proba`` (which indexes ``classes_`` for the positive class -- a
    raw ``predict_proba(x)[:, 1]`` could silently invert). Scoring the whole cohort once and
    slicing per fold is identical to per-fold scoring (``predict_proba`` is row-independent).
    Guards column alignment: a reordered matrix would mislabel the model's coefficients.
    """
    if list(matrix.columns) != list(drug_model.feature_schema.feature_names):
        raise ValueError(
            "feature_matrix columns must equal the model's feature_schema.feature_names in order"
        )
    x = matrix.loc[list(genome_ids)].to_numpy(dtype=np.float64)
    return predict_resistant_proba(drug_model.calibrated_model, x)
