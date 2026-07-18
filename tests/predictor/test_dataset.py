"""Unit tests for genome_firewall.predictor.dataset (EPIC 1 / issues #11-#13).

Every test runs under the autouse ``_no_network`` fixture (tests/conftest.py), so a
green suite here *is* the proof this module never touches a socket — all inputs are
the hand-crafted fixtures under tests/fixtures/bvbrc/, chosen to span every evidence
value, SIR spelling, and edge case documented in the EPIC 1 plan.
"""

from __future__ import annotations

import math
from pathlib import Path

import pandas as pd
import pytest

from genome_firewall.predictor import dataset

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "bvbrc"
FLATFILE = FIXTURES_DIR / "patric_genome_amr_sample.tsv"
METADATA = FIXTURES_DIR / "genome_metadata_sample.tsv"


@pytest.fixture
def raw_df() -> pd.DataFrame:
    """All 22 fixture rows, taxon-filtered (no evidence filter applied yet)."""
    return dataset.parse_amr_flatfile(FLATFILE)


@pytest.fixture
def filtered_df(raw_df: pd.DataFrame) -> pd.DataFrame:
    """The default (evidence=='Laboratory Method', typing-method-required) filter."""
    return dataset.filter_lab_ast(raw_df)


@pytest.fixture
def working_df(filtered_df: pd.DataFrame) -> pd.DataFrame:
    """filtered_df with canonical antibiotic/sir columns attached, pre-collapse."""
    return dataset.attach_canonical_columns(filtered_df)


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


def test_parse_reads_expected_columns(raw_df: pd.DataFrame) -> None:
    assert set(raw_df.columns) >= dataset.REQUIRED_FLATFILE_COLUMNS
    assert len(raw_df) == 22  # every fixture row is taxon_id 573
    assert raw_df["genome_id"].dtype == object  # never coerced to float


def test_parse_missing_column_raises(tmp_path: Path) -> None:
    broken = tmp_path / "broken.tsv"
    broken.write_text("genome_id\tantibiotic\n573.1\tMeropenem\n", encoding="utf-8")
    with pytest.raises(dataset.FlatFileFormatError, match="missing required columns"):
        dataset.parse_amr_flatfile(broken)


def test_parse_taxon_filter_excludes_other_species(tmp_path: Path, raw_df: pd.DataFrame) -> None:
    extra = tmp_path / "mixed.tsv"
    header = "\t".join(raw_df.columns)
    other_species_row = "\t".join(
        "other_species" if col == "genome_id" else ("999" if col == "taxon_id" else "")
        for col in raw_df.columns
    )
    extra.write_text(f"{header}\n{other_species_row}\n", encoding="utf-8")
    parsed = dataset.parse_amr_flatfile(extra, taxon_id=573)
    assert parsed.empty


# ---------------------------------------------------------------------------
# Evidence enumeration & filtering (issue #12)
# ---------------------------------------------------------------------------


def test_enumerate_evidence_lists_all(raw_df: pd.DataFrame) -> None:
    counts = dataset.enumerate_evidence_values(raw_df)
    assert counts["Laboratory Method"] == 20
    assert counts["Computational Method"] == 1
    assert counts["AMR Panel"] == 1  # the unexpected value the report must surface


def test_enumerate_sir_values_incl_legacy(raw_df: pd.DataFrame) -> None:
    counts = dataset.enumerate_sir_values(raw_df)
    assert counts["Resistant"] == 11
    assert counts["Susceptible"] == 4
    assert counts["Sensitive"] == 1
    assert counts["S"] == 1
    assert counts["I"] == 1
    assert counts["Non-susceptible"] == 1
    assert counts["Susceptible-dose dependent"] == 1
    assert counts["<blank>"] == 1


def test_filter_keeps_only_lab(filtered_df: pd.DataFrame) -> None:
    assert len(filtered_df) == 19
    assert set(filtered_df["evidence"].unique()) == {"Laboratory Method"}


def test_filter_drops_computational(raw_df: pd.DataFrame, filtered_df: pd.DataFrame) -> None:
    assert "573.10010" in set(raw_df["genome_id"])
    assert "573.10010" not in set(filtered_df["genome_id"])


def test_filter_drops_empty_typing_method(raw_df: pd.DataFrame, filtered_df: pd.DataFrame) -> None:
    assert "573.10018" in set(raw_df["genome_id"])
    assert "573.10018" not in set(filtered_df["genome_id"])


def test_filter_param_widens_to_amr_panel(raw_df: pd.DataFrame) -> None:
    widened = dataset.filter_lab_ast(raw_df, evidence_values=(dataset.LAB_EVIDENCE, "AMR Panel"))
    assert "573.10011" in set(widened["genome_id"])


# ---------------------------------------------------------------------------
# Canonicalization
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Resistant", "Resistant"),
        ("Susceptible", "Susceptible"),
        ("Sensitive", "Susceptible"),
        ("S", "Susceptible"),
        ("Intermediate", "Intermediate"),
        ("I", "Intermediate"),
        ("Non-susceptible", "Nonsusceptible"),
        ("Nonsusceptible", "Nonsusceptible"),
        ("Susceptible-dose dependent", "Susceptible-dose dependent"),
        ("SDD", "Susceptible-dose dependent"),
        ("", None),
        (None, None),
        ("garbage", None),
    ],
)
def test_canonicalize_sir_legacy(raw: str | None, expected: str | None) -> None:
    assert dataset.canonicalize_sir(raw) == expected


def test_canonicalize_antibiotic_synonyms() -> None:
    assert (
        dataset.canonicalize_antibiotic("Trimethoprim/Sulfamethoxazole")
        == "trimethoprim-sulfamethoxazole"
    )
    assert dataset.canonicalize_antibiotic("SXT") == "trimethoprim-sulfamethoxazole"
    assert dataset.canonicalize_antibiotic("Meropenem") == "meropenem"  # unknown -> passthrough


# ---------------------------------------------------------------------------
# Duplicate resolution & per-drug reporting
# ---------------------------------------------------------------------------


def test_resolve_duplicate_majority(working_df: pd.DataFrame) -> None:
    resolved, _dropped = dataset.resolve_duplicate_labels(working_df)
    row = resolved[(resolved["genome_id"] == "573.10001") & (resolved["antibiotic"] == "meropenem")]
    assert len(row) == 1
    assert row["sir"].iat[0] == "Resistant"  # R, R, S -> R
    assert row["sir_source_rows"].iat[0] == 3
    assert row["sir_n_agree"].iat[0] == 2
    assert math.isclose(row["sir_majority_fraction"].iat[0], 2 / 3)


def test_resolve_duplicate_tie_dropped(working_df: pd.DataFrame) -> None:
    resolved, dropped = dataset.resolve_duplicate_labels(working_df)
    tied = resolved[
        (resolved["genome_id"] == "573.10002") & (resolved["antibiotic"] == "ciprofloxacin")
    ]
    assert tied.empty  # R vs S tie -> dropped, not guessed
    assert len(dropped[dropped["genome_id"] == "573.10002"]) == 2


def test_per_drug_counts_rows_and_unique_genomes(working_df: pd.DataFrame) -> None:
    counts = dataset.per_drug_label_counts(working_df).set_index("antibiotic")
    row = counts.loc["meropenem"]
    assert row["Resistant"] == 3
    assert row["Susceptible"] == 1
    assert row["Nonsusceptible"] == 1
    assert row["total"] == 5
    assert row["n_unique_genomes"] == 3


def test_all_drugs_present_incl_ampicillin(working_df: pd.DataFrame) -> None:
    antibiotics = set(dataset.per_drug_label_counts(working_df)["antibiotic"])
    for drug in (
        "meropenem",
        "ceftriaxone",
        "ciprofloxacin",
        "gentamicin",
        "trimethoprim-sulfamethoxazole",
    ):
        assert drug in antibiotics
    # "ingest all" -- drugs outside the 5-drug MVP panel must not be dropped.
    assert "ampicillin" in antibiotics
    assert "amikacin" in antibiotics
    assert "cefoxitin" in antibiotics


def test_per_drug_standard_breakdown_clsi_eucast(working_df: pd.DataFrame) -> None:
    breakdown = dataset.per_drug_standard_breakdown(working_df).set_index("antibiotic")
    row = breakdown.loc["meropenem"]
    assert row["clsi"] == 3  # rows 1, 3, 19
    assert row["eucast"] == 1  # row 2
    assert row["other_or_blank"] == 1  # row 22 (blank testing_standard)


# ---------------------------------------------------------------------------
# Labels table
# ---------------------------------------------------------------------------


def test_build_labels_schema(filtered_df: pd.DataFrame) -> None:
    labels = dataset.build_labels_table(filtered_df)
    assert list(labels.columns) == list(dataset.LABELS_COLUMNS_CORE)
    assert len(labels) == 14  # 14 resolved genome x antibiotic pairs (see EPIC 1 plan)
    # Intermediate must survive -- 3-class kept; binary collapse is EPIC 3's job.
    intermediate_rows = labels[labels["sir"] == "Intermediate"]
    assert len(intermediate_rows) == 2  # 573.10006 (SXT) and 573.10015 (gentamicin)


def test_intrinsic_ampicillin_retained(filtered_df: pd.DataFrame) -> None:
    labels = dataset.build_labels_table(filtered_df)
    row = labels[(labels["genome_id"] == "573.10007") & (labels["antibiotic"] == "ampicillin")]
    assert len(row) == 1
    assert row["sir"].iat[0] == "Resistant"


def test_build_labels_mic_missing_is_none(filtered_df: pd.DataFrame) -> None:
    labels = dataset.build_labels_table(filtered_df)
    row = labels[(labels["genome_id"] == "573.10019") & (labels["antibiotic"] == "meropenem")]
    assert len(row) == 1
    assert pd.isna(row["mic_value"].iat[0])  # row 22 has no measurement_value


def test_validate_labels_schema_passes_on_marked_labels(filtered_df: pd.DataFrame) -> None:
    labels = dataset.build_labels_table(filtered_df)
    marked = dataset.mark_fasta_availability(labels, {"573.10001"})
    dataset.validate_labels_schema(marked)  # must not raise


def test_validate_labels_schema_rejects_missing_column() -> None:
    broken = pd.DataFrame({"genome_id": ["573.1"]})
    with pytest.raises(AssertionError, match="missing columns"):
        dataset.validate_labels_schema(broken)


def test_mark_fasta_availability(filtered_df: pd.DataFrame) -> None:
    labels = dataset.build_labels_table(filtered_df)
    marked = dataset.mark_fasta_availability(labels, {"573.10001"})
    by_genome = marked.set_index("genome_id")["has_fasta"]
    assert by_genome["573.10001"] is True or bool(by_genome["573.10001"]) is True
    assert bool(by_genome["573.10003"]) is False


def test_select_genome_ids_dedup(filtered_df: pd.DataFrame) -> None:
    labels = dataset.build_labels_table(filtered_df)
    ids = dataset.select_genome_ids(labels)
    assert ids == sorted(set(ids))  # sorted + deduplicated
    assert "573.10001" in ids


def test_select_genome_ids_restricts_to_panel(filtered_df: pd.DataFrame) -> None:
    labels = dataset.build_labels_table(filtered_df)
    ids = dataset.select_genome_ids(labels, antibiotics=("meropenem",))
    assert set(ids) == {"573.10001", "573.10016", "573.10019"}


def test_select_genome_ids_min_n_per_drug(filtered_df: pd.DataFrame) -> None:
    labels = dataset.build_labels_table(filtered_df)
    # meropenem has 3 resolved genomes; a min_n of 4 should exclude it entirely.
    ids = dataset.select_genome_ids(labels, antibiotics=("meropenem",), min_n_per_drug=4)
    assert ids == []


# ---------------------------------------------------------------------------
# MLST / genome metadata
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("kpneumoniae.258", ("kpneumoniae", 258)),
        ("", (None, None)),
        (None, (None, None)),
        ("malformed-value", (None, None)),
    ],
)
def test_parse_mlst_variants(raw: str | None, expected: tuple[str | None, int | None]) -> None:
    assert dataset.parse_mlst(raw) == expected


def test_parse_genome_metadata() -> None:
    metadata = dataset.parse_genome_metadata(METADATA)
    assert len(metadata) == 5
    by_id = metadata.set_index("genome_id")
    assert by_id.loc["573.10001", "mlst_st"] == 258
    assert pd.isna(by_id.loc["573.10002", "mlst_st"])  # blank ST
    assert pd.isna(by_id.loc["573.10005", "mlst_st"])  # malformed ST, fails safe


# ---------------------------------------------------------------------------
# Manifest
# ---------------------------------------------------------------------------


def test_build_manifest_fields(
    raw_df: pd.DataFrame, filtered_df: pd.DataFrame, working_df: pd.DataFrame
) -> None:
    bundle = dataset.build_labels_bundle(filtered_df)
    labels = dataset.mark_fasta_availability(bundle.labels, {"573.10001"})
    genome_metadata = dataset.parse_genome_metadata(METADATA)
    per_drug = dataset.per_drug_label_counts(working_df)
    standard_breakdown = dataset.per_drug_standard_breakdown(working_df)

    manifest = dataset.build_manifest(
        labels=labels,
        working=bundle.working,
        dropped_conflicts=bundle.dropped_conflicts,
        raw_rows=raw_df,
        lab_rows=filtered_df,
        genome_metadata=genome_metadata,
        per_drug=per_drug,
        standard_breakdown=standard_breakdown,
        evidence_counts=dataset.enumerate_evidence_values(raw_df),
        sir_counts_raw=dataset.enumerate_sir_values(raw_df),
        source=dataset.BvbrcSourceInfo(
            ftps_host="ftp.bv-brc.org", amr_flatfile="PATRIC_genome_AMR.txt"
        ),
        created_utc="2026-07-18T00:00:00+00:00",
    )

    assert manifest.counts.raw_rows == 22
    assert manifest.counts.lab_rows == 19
    assert manifest.counts.labels_after_collapse == 14
    assert manifest.counts.dropped_conflict == 2
    assert manifest.counts.dropped_uncanonical_sir == 1
    assert manifest.counts.genomes_with_fasta == 1

    assert manifest.evidence_vocabulary["Laboratory Method"] == 20
    assert manifest.evidence_vocabulary["Computational Method"] == 1
    assert manifest.evidence_vocabulary["AMR Panel"] == 1

    assert manifest.mlst.genomes_total == 5
    assert manifest.mlst.with_st == 3
    assert manifest.mlst.missing_st == 2
    assert math.isclose(manifest.mlst.missing_fraction, 0.4)

    meropenem = next(e for e in manifest.per_drug if e.antibiotic == "meropenem")
    assert meropenem.resistant == 3
    assert meropenem.total == 5
    assert meropenem.clsi == 3
    assert meropenem.eucast == 1

    ciprofloxacin = next(e for e in manifest.per_drug if e.antibiotic == "ciprofloxacin")
    assert ciprofloxacin.dropped_conflict == 2


def test_manifest_rejects_unknown_field() -> None:
    with pytest.raises(Exception, match="extra"):
        dataset.BvbrcSourceInfo(
            ftps_host="ftp.bv-brc.org", amr_flatfile="x.txt", unexpected_field="nope"
        )


# ---------------------------------------------------------------------------
# No-network invariant
# ---------------------------------------------------------------------------


def test_dataset_module_tests_run_under_no_network_guard() -> None:
    """Documents the invariant this whole file relies on: the autouse `_no_network`
    fixture (tests/conftest.py) blocks socket creation, so every test above running
    to completion is itself proof genome_firewall.predictor.dataset never touches a
    socket."""
    import socket

    with pytest.raises(RuntimeError, match="network access is disabled"):
        socket.socket()
