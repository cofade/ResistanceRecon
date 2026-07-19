"""Tests for the binary SIR collapse policy (ADR-0017, issue #18 support)."""

from __future__ import annotations

import pandas as pd

from genome_firewall.predictor.dataset import collapse_sir_to_binary, mlst_group_id


def test_collapse_keeps_only_resistant_and_susceptible() -> None:
    df = pd.DataFrame(
        {
            "genome_id": ["g1", "g2", "g3", "g4", "g5"],
            "antibiotic": ["meropenem"] * 5,
            "sir": [
                "Resistant",
                "Susceptible",
                "Intermediate",
                "Nonsusceptible",
                "Susceptible-dose dependent",
            ],
        }
    )
    out = collapse_sir_to_binary(df)
    assert set(out["sir_binary"]) == {"R", "S"}
    assert sorted(out["genome_id"]) == ["g1", "g2"]
    assert out.loc[out["genome_id"] == "g1", "sir_binary"].iloc[0] == "R"
    assert out.loc[out["genome_id"] == "g2", "sir_binary"].iloc[0] == "S"


def test_collapse_does_not_mutate_input() -> None:
    df = pd.DataFrame({"genome_id": ["g1"], "antibiotic": ["meropenem"], "sir": ["Resistant"]})
    _ = collapse_sir_to_binary(df)
    assert "sir_binary" not in df.columns


def test_collapse_drops_null_sir() -> None:
    df = pd.DataFrame(
        {
            "genome_id": ["g1", "g2"],
            "antibiotic": ["meropenem", "meropenem"],
            "sir": ["Resistant", None],
        }
    )
    out = collapse_sir_to_binary(df)
    assert list(out["genome_id"]) == ["g1"]


def test_mlst_group_id_uses_st_when_present_else_singleton() -> None:
    assert mlst_group_id("kpneumoniae", "258", "g1") == "st:kpneumoniae:258"
    # parquet round-trip float form
    assert mlst_group_id("kpneumoniae", 258.0, "g1") == "st:kpneumoniae:258"
    assert mlst_group_id(None, None, "g9") == "singleton:g9"
    assert mlst_group_id("kpneumoniae", float("nan"), "g9") == "singleton:g9"
