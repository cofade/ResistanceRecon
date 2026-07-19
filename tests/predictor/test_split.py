"""Tests for the homology-aware grouped split (ADR-0005) -- the highest-value correctness
item. No-leakage and min-n are pinned first and hardest."""

from __future__ import annotations

import pandas as pd
import pytest

from genome_firewall.predictor.split import (
    LeakageError,
    MlstStBackend,
    any_degraded,
    evaluate_min_n,
    leave_one_group_out_holdout,
    make_grouped_folds,
    make_split,
    no_leakage_check,
    per_fold_class_balance,
)


def _wellformed_cohort(
    n_groups: int = 16, per_group: int = 5
) -> tuple[list[str], list[str], pd.DataFrame]:
    """Every ST carries both R and S, comfortably above the min-n gate."""
    genome_ids: list[str] = []
    y: list[str] = []
    meta_rows: list[tuple[str, str, str]] = []
    for group_index in range(n_groups):
        st = str(1000 + group_index)
        for member in range(per_group):
            gid = f"g{group_index}_{member}"
            genome_ids.append(gid)
            y.append("R" if member % 2 == 0 else "S")
            meta_rows.append((gid, "kpneumoniae", st))
    metadata = pd.DataFrame(meta_rows, columns=["genome_id", "mlst_scheme", "mlst_st"])
    return genome_ids, y, metadata


def _groups_for(genome_ids: list[str], metadata: pd.DataFrame) -> list[str]:
    group_map = MlstStBackend().assign_groups(genome_ids, metadata)
    return [group_map[gid] for gid in genome_ids]


# --- no_leakage_check (the hard guarantee) ---------------------------------------------


def test_no_leakage_check_passes_for_disjoint_groups() -> None:
    groups = ["a", "a", "b", "b", "c"]
    no_leakage_check(groups, [0, 1], [2, 3], [4])  # no raise


def test_no_leakage_check_raises_when_a_group_straddles_two_sets() -> None:
    groups = ["a", "a", "b", "b"]
    with pytest.raises(LeakageError, match="leakage"):
        no_leakage_check(groups, [0], [1])  # index 0 and 1 are both group 'a'


def test_make_split_boundaries_are_group_disjoint_and_partition_the_cohort() -> None:
    genome_ids, y, metadata = _wellformed_cohort()
    groups = _groups_for(genome_ids, metadata)
    result = make_split(genome_ids, y, metadata, antibiotic="meropenem", seed=0)
    assert result.min_n.ok is True
    assert result.split is not None and result.holdout is not None

    sets = {
        "train": set(result.split.train_index),
        "cal": set(result.split.calibration_index),
        "test": set(result.split.test_index),
        "holdout": set(result.holdout.holdout_index),
    }
    # indices partition the whole cohort
    assert set().union(*sets.values()) == set(range(len(genome_ids)))
    total = sum(len(s) for s in sets.values())
    assert total == len(genome_ids)  # disjoint by count

    # and NO homology group straddles any two of the four boundaries
    group_sets = {name: {groups[i] for i in idxs} for name, idxs in sets.items()}
    names = list(group_sets)
    for a_index in range(len(names)):
        for b_index in range(a_index + 1, len(names)):
            assert group_sets[names[a_index]].isdisjoint(group_sets[names[b_index]])


# --- min-n gate ------------------------------------------------------------------------


def test_evaluate_min_n_flags_insufficient_susceptible() -> None:
    y = ["R"] * 25 + ["S"] * 5
    result = evaluate_min_n(y)
    assert result.ok is False
    assert result.n_resistant == 25 and result.n_susceptible == 5
    assert result.reason is not None


def test_make_split_short_circuits_on_min_n_failure() -> None:
    genome_ids = [f"g{i}" for i in range(30)]
    y = ["R"] * 25 + ["S"] * 5  # only 5 S -> below the gate
    metadata = pd.DataFrame(
        {"genome_id": genome_ids, "mlst_scheme": [None] * 30, "mlst_st": [None] * 30}
    )
    result = make_split(genome_ids, y, metadata, antibiotic="gentamicin")
    assert result.min_n.ok is False
    assert result.split is None and result.holdout is None


# --- StratifiedGroupKFold degradation guard -------------------------------------------


def test_per_fold_balance_flags_dominant_clone_degradation() -> None:
    # One dominant ST holds ALL resistant isolates; susceptibles are singletons. Any fold
    # placing the dominant clone in train leaves its test set with zero R -> degraded.
    y = ["R"] * 24 + ["S"] * 24
    groups = ["st:kpneumoniae:258"] * 24 + [f"singleton:s{i}" for i in range(24)]
    folds = make_grouped_folds(y, groups, n_splits=4, seed=0)
    balances = per_fold_class_balance(folds, y)
    assert any_degraded(balances) is True


# --- unseen-lineage holdout + backend --------------------------------------------------


def test_holdout_prefers_a_both_class_group_and_is_disjoint() -> None:
    y = ["R", "S", "R", "S", "R"]
    groups = ["g1", "g1", "g2", "g2", "g3"]  # g1/g2 both-class, g3 single-class
    holdout = leave_one_group_out_holdout(y, groups)
    assert holdout.holdout_group in {"g1", "g2"}
    assert set(holdout.holdout_index).isdisjoint(set(holdout.remaining_index))


def test_mlst_backend_uses_st_then_singleton_fallback() -> None:
    metadata = pd.DataFrame(
        {
            "genome_id": ["g1", "g2"],
            "mlst_scheme": ["kpneumoniae", None],
            "mlst_st": ["258", None],
        }
    )
    groups = MlstStBackend().assign_groups(["g1", "g2", "g3"], metadata)
    assert groups["g1"] == "st:kpneumoniae:258"
    assert groups["g2"] == "singleton:g2"
    assert groups["g3"] == "singleton:g3"  # absent from metadata entirely
