"""Tests for capped, stratified genome-subset selection (issue #18 support)."""

from __future__ import annotations

import pandas as pd

from genome_firewall.predictor.subset import SubsetSelection, select_capped_stratified_subset


def _labels(rows: list[tuple[str, str, str]]) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=["genome_id", "antibiotic", "sir"])


def _metadata(rows: list[tuple[str, object, object]]) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=["genome_id", "mlst_scheme", "mlst_st"])


def _cohort() -> tuple[pd.DataFrame, pd.DataFrame]:
    label_rows = [(f"clone{i}", "meropenem", "Resistant") for i in range(1, 6)]
    label_rows += [(f"sing{i}", "meropenem", "Susceptible") for i in range(1, 6)]
    meta_rows: list[tuple[str, object, object]] = [
        (f"clone{i}", "kpneumoniae", "258") for i in range(1, 6)
    ]
    meta_rows += [(f"sing{i}", None, None) for i in range(1, 6)]
    return _labels(label_rows), _metadata(meta_rows)


def test_subset_respects_cap_and_per_st_fraction() -> None:
    labels, metadata = _cohort()
    sel = select_capped_stratified_subset(
        labels,
        metadata,
        cap=6,
        antibiotics=("meropenem",),
        per_drug_target=2,
        max_per_st_fraction=0.5,
    )
    assert isinstance(sel, SubsetSelection)
    assert sel.n_selected <= 6
    # st_cap = int(0.5 * 6) = 3 -- the ST258 clone must not dominate the subset.
    assert sel.per_group_counts.get("st:kpneumoniae:258", 0) <= 3


def test_subset_is_deterministic() -> None:
    labels, metadata = _cohort()
    a = select_capped_stratified_subset(
        labels, metadata, cap=6, antibiotics=("meropenem",), per_drug_target=2
    )
    b = select_capped_stratified_subset(
        labels, metadata, cap=6, antibiotics=("meropenem",), per_drug_target=2
    )
    assert a.genome_ids == b.genome_ids


def test_subset_meets_target_when_data_allows() -> None:
    labels, metadata = _cohort()
    sel = select_capped_stratified_subset(
        labels,
        metadata,
        cap=8,
        antibiotics=("meropenem",),
        per_drug_target=2,
        max_per_st_fraction=0.5,
    )
    assert sel.per_cell_counts.get("meropenem|R", 0) >= 2
    assert sel.per_cell_counts.get("meropenem|S", 0) >= 2
    assert "meropenem" in sel.drugs_meeting_target


def test_subset_flags_drug_below_target() -> None:
    labels = _labels(
        [
            ("g1", "gentamicin", "Resistant"),
            ("g2", "gentamicin", "Susceptible"),
            ("g3", "gentamicin", "Susceptible"),
        ]
    )
    metadata = _metadata([("g1", None, None), ("g2", None, None), ("g3", None, None)])
    sel = select_capped_stratified_subset(
        labels,
        metadata,
        cap=10,
        antibiotics=("gentamicin",),
        per_drug_target=5,
        max_per_st_fraction=1.0,
    )
    assert "gentamicin" in sel.drugs_below_target  # only 1 R available, target 5


def test_subset_drops_ambiguous_labels() -> None:
    labels = _labels(
        [
            ("g1", "meropenem", "Intermediate"),
            ("g2", "meropenem", "Nonsusceptible"),
            ("g3", "meropenem", "Susceptible-dose dependent"),
        ]
    )
    metadata = _metadata([("g1", None, None), ("g2", None, None), ("g3", None, None)])
    sel = select_capped_stratified_subset(
        labels,
        metadata,
        cap=10,
        antibiotics=("meropenem",),
        per_drug_target=2,
        max_per_st_fraction=1.0,
    )
    assert sel.n_selected == 0  # all rows dropped by the binary collapse
