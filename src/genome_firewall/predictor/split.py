"""Homology-aware grouped train/calibration/test split + no-leakage guarantee (issue #18).

ADR-0005 -- the project's highest-value correctness item. Near-identical clonal genomes
must never straddle a train/test boundary, or held-out accuracy is inflated and the model
is merely memorising clones. Genomes are grouped by MLST sequence type
(``dataset.mlst_group_id``); genomes without a usable ST fall back to their own singleton
group (ADR-0015 -- leakage-safe, needs no external tool; real Mash/skani ANI-99.5%
clustering is deferred behind :class:`AniClusterBackend`). Every split boundary is then
group-disjoint, and :func:`no_leakage_check` enforces it.

Pure and LLM-free (predictor/ is trust-critical -- scripts/check_import_boundary.py forbids
importing genome_firewall.llm here). scikit-learn's ``StratifiedGroupKFold`` does the
grouped folding; :func:`per_fold_class_balance` reports when a dominant clone (e.g.
ST258/ST512) has degraded it toward plain ``GroupKFold`` (a fold left with no minority
class), so that risk is surfaced rather than hidden.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Sequence
from typing import Protocol

import numpy as np
import pandas as pd
from pydantic import BaseModel, ConfigDict
from sklearn.model_selection import StratifiedGroupKFold

from genome_firewall.constants import MIN_RESISTANT_PER_DRUG, MIN_SUSCEPTIBLE_PER_DRUG
from genome_firewall.predictor.dataset import mlst_group_id

#: A drug needs at least this many DISTINCT homology groups to form a leakage-safe grouped
#: holdout + train/calibration/test split. Fewer means the labels are too clonal to split
#: without a group straddling a boundary -- reported as insufficient data, never crashed on
#: (StratifiedGroupKFold raises when n_splits exceeds the group count). The real-data failure
#: mode: a thin drug whose labels concentrate in one or two dominant STs (ST258/ST512/ST11).
MIN_DISTINCT_GROUPS = 4


class LeakageError(RuntimeError):
    """Raised when a homology group would appear on both sides of a split boundary."""


class _Frozen(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Fold(_Frozen):
    """One grouped CV fold, as positional indices into the aligned genome list."""

    train_index: tuple[int, ...]
    test_index: tuple[int, ...]


class ThreeWaySplit(_Frozen):
    """Group-disjoint train / calibration / test indices (positional).

    ``calibration_index`` is the homology-grouped fold both sigmoid calibration
    (``cv='prefit'``, ADR-0004) and conformal quantile fitting use; ``test_index`` is the
    reported marginal metric set.
    """

    train_index: tuple[int, ...]
    calibration_index: tuple[int, ...]
    test_index: tuple[int, ...]


class HoldoutSpec(_Frozen):
    """One entire homology group reserved as the unseen-lineage generalization set."""

    holdout_group: str
    holdout_index: tuple[int, ...]
    remaining_index: tuple[int, ...]


class FoldBalance(_Frozen):
    """Per-fold R/S counts -- the ADR-0005 degradation guard."""

    fold: int
    n_train: int
    n_test: int
    train_resistant: int
    train_susceptible: int
    test_resistant: int
    test_susceptible: int
    #: True when any of the four cells is empty -- StratifiedGroupKFold has degraded toward
    #: GroupKFold on this fold (a dominant clone soaking up one class).
    degraded: bool


class MinNGateResult(_Frozen):
    """Whether a drug clears the min-n gate (>=20 R AND >=20 S; ADR-0004)."""

    ok: bool
    n_resistant: int
    n_susceptible: int
    reason: str | None = None


class SplitResult(_Frozen):
    """The full homology-aware split for one antibiotic, plus its provenance.

    ``holdout`` / ``split`` are None when the drug fails the min-n gate (no model is built);
    ``min_n.ok`` is the flag callers branch on.
    """

    antibiotic: str
    backend: str
    seed: int
    n_groups: int
    min_n: MinNGateResult
    holdout: HoldoutSpec | None = None
    split: ThreeWaySplit | None = None
    fold_balance: tuple[FoldBalance, ...] = ()
    degraded: bool = False
    #: Why no model can be built (min-n failure OR too-clonal to split); None when ok. Note
    #: min_n.ok reflects the R/S COUNT gate only -- a drug can clear it yet still be reported
    #: insufficient (split is None) for lack of homology-group diversity.
    reason: str | None = None


class ClusterBackend(Protocol):
    """Assigns each genome_id a homology-group id used for the grouped split."""

    name: str

    def assign_groups(
        self, genome_ids: Sequence[str], metadata: pd.DataFrame
    ) -> dict[str, str]: ...


class MlstStBackend:
    """MLST-ST-primary grouping with a singleton fallback (ADR-0005 + ADR-0015)."""

    name = "mlst_st"

    def assign_groups(self, genome_ids: Sequence[str], metadata: pd.DataFrame) -> dict[str, str]:
        lookup: dict[str, tuple[object, object]] = {}
        meta = metadata.reset_index(drop=True)
        if "genome_id" in meta.columns:
            gids = meta["genome_id"].astype(str).tolist()
            count = len(gids)
            schemes = (
                meta["mlst_scheme"].tolist() if "mlst_scheme" in meta.columns else [None] * count
            )
            sts = meta["mlst_st"].tolist() if "mlst_st" in meta.columns else [None] * count
            for gid, scheme, st in zip(gids, schemes, sts, strict=True):
                lookup.setdefault(gid, (scheme, st))
        result: dict[str, str] = {}
        for gid in genome_ids:
            scheme, st = lookup.get(gid, (None, None))
            result[gid] = mlst_group_id(scheme, st, gid)
        return result


class AniClusterBackend:
    """Deferred: real Mash/skani ANI-99.5% single-linkage clustering for missing-ST genomes.

    ADR-0015 records the deferral and names the owning follow-up issue; MlstStBackend's
    singleton fallback is the leakage-safe interim, so nothing this epic needs it.
    """

    name = "ani"

    def assign_groups(self, genome_ids: Sequence[str], metadata: pd.DataFrame) -> dict[str, str]:
        raise NotImplementedError(
            "ANI clustering (Mash/skani) is deferred -- use MlstStBackend; see ADR-0015"
        )


def safe_n_splits(y: Sequence[object], groups: Sequence[str], requested: int) -> int:
    """Cap n_splits at the number of groups and the minority-class count (StratifiedGroupKFold
    cannot make more folds than either), never below 2. ``y`` may be str or int labels."""
    n_groups = len(set(groups))
    class_counts = Counter(y)
    min_class = min(class_counts.values()) if class_counts else 0
    return max(2, min(requested, n_groups, min_class))


def make_grouped_folds(
    y: Sequence[str], groups: Sequence[str], *, n_splits: int = 5, seed: int = 0
) -> list[Fold]:
    """Grouped, stratified CV folds (positional indices) via StratifiedGroupKFold."""
    y_list = list(y)
    groups_list = list(groups)
    n = len(y_list)
    k = safe_n_splits(y_list, groups_list, n_splits)
    splitter = StratifiedGroupKFold(n_splits=k, shuffle=True, random_state=seed)
    folds: list[Fold] = []
    for train_idx, test_idx in splitter.split(np.zeros(n), y_list, groups_list):
        folds.append(
            Fold(
                train_index=tuple(int(i) for i in train_idx),
                test_index=tuple(int(i) for i in test_idx),
            )
        )
    return folds


def three_way_grouped_split(
    y: Sequence[str], groups: Sequence[str], *, n_splits: int = 5, seed: int = 0
) -> ThreeWaySplit:
    """Peel a group-disjoint test fold, then a calibration fold from the remainder, leaving
    train -- all three group-disjoint by StratifiedGroupKFold's whole-group guarantee."""
    y_list = list(y)
    groups_list = list(groups)
    n = len(y_list)
    k_outer = safe_n_splits(y_list, groups_list, n_splits)
    outer = StratifiedGroupKFold(n_splits=k_outer, shuffle=True, random_state=seed)
    train_val_idx, test_idx = next(iter(outer.split(np.zeros(n), y_list, groups_list)))

    y_tv = [y_list[i] for i in train_val_idx]
    groups_tv = [groups_list[i] for i in train_val_idx]
    k_inner = safe_n_splits(y_tv, groups_tv, n_splits)
    inner = StratifiedGroupKFold(n_splits=k_inner, shuffle=True, random_state=seed + 1)
    train_local, cal_local = next(iter(inner.split(np.zeros(len(y_tv)), y_tv, groups_tv)))

    return ThreeWaySplit(
        train_index=tuple(int(train_val_idx[i]) for i in train_local),
        calibration_index=tuple(int(train_val_idx[i]) for i in cal_local),
        test_index=tuple(int(i) for i in test_idx),
    )


def leave_one_group_out_holdout(y: Sequence[str], groups: Sequence[str]) -> HoldoutSpec:
    """Reserve one entire homology group as the unseen-lineage generalization set.

    Deterministic: prefer a group carrying both R and S (so the holdout metric is
    meaningful), then the largest such group, tie-broken by group id.
    """
    groups_list = list(groups)
    by_group: dict[str, list[int]] = defaultdict(list)
    classes: dict[str, set[str]] = defaultdict(set)
    for i, group in enumerate(groups_list):
        by_group[group].append(i)
        classes[group].add(y[i])
    both = [group for group in by_group if len(classes[group]) >= 2]
    pool = both if both else list(by_group)
    chosen = max(sorted(pool), key=lambda group: len(by_group[group]))
    holdout_index = tuple(by_group[chosen])
    holdout_set = set(holdout_index)
    remaining = tuple(i for i in range(len(groups_list)) if i not in holdout_set)
    return HoldoutSpec(holdout_group=chosen, holdout_index=holdout_index, remaining_index=remaining)


def per_fold_class_balance(folds: Sequence[Fold], y: Sequence[str]) -> list[FoldBalance]:
    """Per-fold R/S counts, flagging any fold degraded toward GroupKFold (an empty cell)."""
    y_list = list(y)
    balances: list[FoldBalance] = []
    for index, fold in enumerate(folds):
        train = [y_list[i] for i in fold.train_index]
        test = [y_list[i] for i in fold.test_index]
        train_r, train_s = train.count("R"), train.count("S")
        test_r, test_s = test.count("R"), test.count("S")
        balances.append(
            FoldBalance(
                fold=index,
                n_train=len(train),
                n_test=len(test),
                train_resistant=train_r,
                train_susceptible=train_s,
                test_resistant=test_r,
                test_susceptible=test_s,
                degraded=min(train_r, train_s, test_r, test_s) == 0,
            )
        )
    return balances


def any_degraded(balances: Sequence[FoldBalance]) -> bool:
    return any(balance.degraded for balance in balances)


def no_leakage_check(groups: Sequence[str], *index_sets: Sequence[int]) -> None:
    """Raise LeakageError if any homology group appears in more than one index set.

    The single hard guarantee behind ADR-0005: train / calibration / test / unseen-holdout
    must be group-disjoint, so no near-clone straddles a split boundary.
    """
    owner: dict[str, int] = {}
    for set_id, indices in enumerate(index_sets):
        for i in indices:
            group = groups[i]
            if group in owner and owner[group] != set_id:
                raise LeakageError(
                    f"homology group {group!r} appears in index sets "
                    f"{owner[group]} and {set_id} -- train/test leakage"
                )
            owner[group] = set_id


def evaluate_min_n(
    y: Sequence[str],
    *,
    min_resistant: int = MIN_RESISTANT_PER_DRUG,
    min_susceptible: int = MIN_SUSCEPTIBLE_PER_DRUG,
) -> MinNGateResult:
    """Min-n gate: a drug needs >=min_resistant R AND >=min_susceptible S, else it is out of
    scope (reported 'insufficient data', never given an unreliable model)."""
    labels = list(y)
    n_r = labels.count("R")
    n_s = labels.count("S")
    ok = n_r >= min_resistant and n_s >= min_susceptible
    reason = (
        None
        if ok
        else (
            f"insufficient data: need >={min_resistant} R and >={min_susceptible} S, "
            f"have {n_r} R / {n_s} S"
        )
    )
    return MinNGateResult(ok=ok, n_resistant=n_r, n_susceptible=n_s, reason=reason)


def make_split(
    genome_ids: Sequence[str],
    y: Sequence[str],
    metadata: pd.DataFrame,
    *,
    antibiotic: str,
    backend: ClusterBackend | None = None,
    n_splits: int = 5,
    seed: int = 0,
) -> SplitResult:
    """Compose the full split for one drug: assign groups, gate on min-n, reserve the
    unseen-lineage holdout, three-way-split the remainder, and enforce no leakage.

    Returns an insufficient-data ``SplitResult`` (no holdout/split) when the drug fails the
    min-n gate. All indices are positional into ``genome_ids``/``y`` (which must align).
    """
    if len(genome_ids) != len(y):
        raise ValueError("genome_ids and y must align")
    resolved_backend: ClusterBackend = backend if backend is not None else MlstStBackend()
    backend_name = getattr(resolved_backend, "name", resolved_backend.__class__.__name__)
    group_map = resolved_backend.assign_groups(genome_ids, metadata)
    groups = [group_map[gid] for gid in genome_ids]
    n_groups = len(set(groups))

    min_n = evaluate_min_n(y)

    def _insufficient(reason: str) -> SplitResult:
        # No model can be built. min_n is left untouched (it reports only the R/S COUNT gate);
        # `reason` carries the actual cause (count failure or too-clonal-to-split). split stays
        # None, which is what train_one_antibiotic branches on.
        return SplitResult(
            antibiotic=antibiotic,
            backend=backend_name,
            seed=seed,
            n_groups=n_groups,
            min_n=min_n,
            reason=reason,
        )

    if not min_n.ok:
        return _insufficient(min_n.reason or "insufficient min-n")

    if n_groups < MIN_DISTINCT_GROUPS:
        return _insufficient(
            f"insufficient homology-group diversity: {n_groups} distinct group(s) < "
            f"{MIN_DISTINCT_GROUPS} needed for a leakage-safe grouped holdout + "
            "train/calibration/test split (labels too clonal to split without leakage)"
        )

    holdout = leave_one_group_out_holdout(y, groups)
    remaining = list(holdout.remaining_index)
    y_rem = [y[i] for i in remaining]
    groups_rem = [groups[i] for i in remaining]
    # Scope the try tightly to the ONLY call that can raise the too-clonal ValueError
    # (StratifiedGroupKFold). A Pydantic ValidationError from ThreeWaySplit -- also a
    # ValueError -- must surface, not be laundered into insufficient_data, so its construction
    # is outside the try. A genuine leak raises LeakageError (a RuntimeError) and is unaffected.
    try:
        local = three_way_grouped_split(y_rem, groups_rem, n_splits=n_splits, seed=seed)
    except ValueError as exc:
        return _insufficient(f"grouped split could not be formed (too clonal/imbalanced): {exc}")

    split = ThreeWaySplit(
        train_index=tuple(remaining[i] for i in local.train_index),
        calibration_index=tuple(remaining[i] for i in local.calibration_index),
        test_index=tuple(remaining[i] for i in local.test_index),
    )
    no_leakage_check(
        groups,
        split.train_index,
        split.calibration_index,
        split.test_index,
        holdout.holdout_index,
    )

    train_y = [y[i] for i in split.train_index]
    train_groups = [groups[i] for i in split.train_index]
    try:
        inner_folds = make_grouped_folds(train_y, train_groups, n_splits=n_splits, seed=seed)
    except ValueError as exc:
        return _insufficient(f"inner CV folds could not be formed (too clonal/imbalanced): {exc}")

    balances = per_fold_class_balance(inner_folds, train_y)

    return SplitResult(
        antibiotic=antibiotic,
        backend=backend_name,
        seed=seed,
        n_groups=n_groups,
        min_n=min_n,
        holdout=holdout,
        split=split,
        fold_balance=tuple(balances),
        degraded=any_degraded(balances),
    )
