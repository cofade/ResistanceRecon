"""BV-BRC lab-AST label ingestion (EPIC 1 / issues #11-#13).

Pure, network-free transforms: parse the BV-BRC ``PATRIC_genome_AMR`` flat file, enumerate
and filter on the ``evidence`` field (golden rule #3 — never a claim without traceable
evidence; only ``evidence == 'Laboratory Method'`` rows are genuine wet-lab ground truth,
see ADR-0001), canonicalize SIR phenotypes and antibiotic names, collapse duplicate
genome x antibiotic measurements, and assemble the on-disk ``labels`` table + provenance
manifest.

All network I/O (FTPS download, Solr Data API cross-check) lives in
``scripts/fetch_bvbrc_data.py`` / ``scripts/build_dataset.py`` — never here. This module
must not import ``genome_firewall.llm`` (enforced by scripts/check_import_boundary.py) and
is exercised entirely against committed fixtures under the autouse ``_no_network`` guard
(see tests/conftest.py) — a green test suite for this module *is* the proof it never
touches a socket.

Schema-validation policy: at ~85k raw rows, per-row Pydantic validation is unnecessary
overhead; ``LABELS_COLUMNS`` + :func:`validate_labels_schema` is the lightweight column
contract instead. The one Pydantic model here, :class:`DatasetManifest`, crosses the
script<->analysis boundary (golden rule #5 — no raw dicts across module boundaries) and
will move into ``schemas.py`` once EPIC 2 introduces it.
"""

from __future__ import annotations

import platform
import re
from collections.abc import Collection
from datetime import UTC, datetime
from pathlib import Path
from typing import Final, NamedTuple

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field

from genome_firewall.constants import KLEBSIELLA_PNEUMONIAE_TAXON_ID

# ---------------------------------------------------------------------------
# Vocabulary & column contracts
# ---------------------------------------------------------------------------

#: The only evidence value ADR-0001 treats as genuine wet-lab ground truth.
LAB_EVIDENCE: Final[str] = "Laboratory Method"
#: The evidence value the challenge explicitly warns against (model-generated).
COMPUTATIONAL_EVIDENCE: Final[str] = "Computational Method"

#: Canonical SIR classes. Multi-class (3-class + rare buckets) is kept through EPIC 1;
#: the binary drop-Intermediate collapse for training is EPIC 3's responsibility.
SIR_CLASSES: Final[tuple[str, ...]] = (
    "Resistant",
    "Susceptible",
    "Intermediate",
    "Nonsusceptible",
    "Susceptible-dose dependent",
)

#: The two clinically opposed sides of the SIR spectrum, used by resolve_duplicate_labels
#: to detect a genuine contradiction. Nonsusceptible is defined as "not susceptible" (as
#: sharp an opposite of Susceptible as Resistant is) and Susceptible-dose-dependent is a
#: susceptibility category (as sharp an opposite of Resistant as plain Susceptible is).
#: Intermediate sits in neither side deliberately -- it does not contradict either sharply.
_SUSCEPTIBLE_SIDE: Final[frozenset[str]] = frozenset({"Susceptible", "Susceptible-dose dependent"})
_RESISTANT_SIDE: Final[frozenset[str]] = frozenset({"Resistant", "Nonsusceptible"})

# Every SIR class except Intermediate MUST be assigned to exactly one side above, or
# resolve_duplicate_labels silently lets a real contradiction through undetected (the
# exact bug found and re-found across three review rounds). An `if`/`raise` (not
# `assert`) so this guard survives even under `python -O`, which strips asserts.
if set(SIR_CLASSES) - {"Intermediate"} != _SUSCEPTIBLE_SIDE | _RESISTANT_SIDE:
    raise AssertionError(
        "a SIR class is missing from _SUSCEPTIBLE_SIDE/_RESISTANT_SIDE -- "
        "see resolve_duplicate_labels"
    )

#: Columns the raw PATRIC_genome_AMR flat file must have. A missing column signals a
#: BV-BRC schema change or the wrong filename (PATRIC_genome_AMR.txt vs
#: PATRIC_genomes_AMR.txt — see Documentation/research-findings/bv-brc-data-access.md).
REQUIRED_FLATFILE_COLUMNS: Final[frozenset[str]] = frozenset(
    {
        "genome_id",
        "genome_name",
        "taxon_id",
        "antibiotic",
        "resistant_phenotype",
        "evidence",
        "laboratory_typing_method",
        "measurement",
        "measurement_value",
        "measurement_unit",
        "testing_standard",
        "testing_standard_year",
    }
)

#: Columns the BV-BRC genome_metadata flat file must have.
REQUIRED_METADATA_COLUMNS: Final[frozenset[str]] = frozenset(
    {"genome_id", "genome_name", "taxon_id"}
)

#: Columns produced by build_labels_table (pre has_fasta — see mark_fasta_availability).
LABELS_COLUMNS_CORE: Final[tuple[str, ...]] = (
    "genome_id",
    "antibiotic",
    "sir",
    "sir_source_rows",
    "sir_n_agree",
    "sir_majority_fraction",
    "mic_value",
    "mic_sign",
    "mic_unit",
    "dominant_testing_standard",
    "testing_standard_year_min",
    "testing_standard_year_max",
    "lab_typing_methods",
)

#: Full data/processed/labels.parquet column contract (see Documentation/01-introduction-
#: and-goals/prd.md Artifacts). ``has_fasta`` is attached in Phase B (mark_fasta_availability).
LABELS_COLUMNS: Final[tuple[str, ...]] = (*LABELS_COLUMNS_CORE, "has_fasta")

_SIR_ALIASES: Final[dict[str, str]] = {
    "resistant": "Resistant",
    "r": "Resistant",
    "susceptible": "Susceptible",
    "sensitive": "Susceptible",
    "s": "Susceptible",
    "intermediate": "Intermediate",
    "i": "Intermediate",
    "nonsusceptible": "Nonsusceptible",
    "non-susceptible": "Nonsusceptible",
    "non susceptible": "Nonsusceptible",
    "ns": "Nonsusceptible",
    "susceptible-dose dependent": "Susceptible-dose dependent",
    "susceptible-dose-dependent": "Susceptible-dose dependent",
    "sdd": "Susceptible-dose dependent",
}

#: Known spelling/abbreviation variants for antibiotics with especially inconsistent
#: naming in BV-BRC (trimethoprim-sulfamethoxazole is the worst offender). Every other
#: antibiotic passes through lowercased/stripped — ALL drugs are ingested, not just the
#: 5-drug MVP panel (constants.SUPPORTED_ANTIBIOTICS is a downstream filter, not here).
_ANTIBIOTIC_ALIASES: Final[dict[str, str]] = {
    "trimethoprim/sulfamethoxazole": "trimethoprim-sulfamethoxazole",
    "sulfamethoxazole/trimethoprim": "trimethoprim-sulfamethoxazole",
    "trimethoprim-sulfamethoxazole": "trimethoprim-sulfamethoxazole",
    "co-trimoxazole": "trimethoprim-sulfamethoxazole",
    "cotrimoxazole": "trimethoprim-sulfamethoxazole",
    "sxt": "trimethoprim-sulfamethoxazole",
    "tmp-smx": "trimethoprim-sulfamethoxazole",
    "tmp/smx": "trimethoprim-sulfamethoxazole",
}

_MLST_RE: Final[re.Pattern[str]] = re.compile(r"^([A-Za-z0-9_]+)\.(\d+)$")
_MIC_SIGN_RE: Final[re.Pattern[str]] = re.compile(r"^\s*(<=|>=|<|>|=)")


class FlatFileFormatError(ValueError):
    """Raised when a BV-BRC flat file is missing expected columns.

    Signals a schema change or a wrong filename, not a data-content problem — see
    Documentation/research-findings/bv-brc-data-access.md for the filename risk
    (``PATRIC_genome_AMR.txt`` vs ``PATRIC_genomes_AMR.txt``).
    """


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Lowercase/strip/underscore-ify column headers so downstream code can rely on
    stable snake_case names regardless of minor header formatting differences."""
    out = df.copy()
    out.columns = [str(c).strip().lower().replace(" ", "_") for c in out.columns]
    return out


def parse_amr_flatfile(
    path: Path, *, taxon_id: int | None = KLEBSIELLA_PNEUMONIAE_TAXON_ID
) -> pd.DataFrame:
    """Read the tab-delimited BV-BRC ``PATRIC_genome_AMR`` flat file.

    Every column is read as ``str`` (never inferred) so genome_id values such as
    ``"573.10169"`` are never coerced to float. Raises FlatFileFormatError if
    REQUIRED_FLATFILE_COLUMNS is missing. Optionally filters to one NCBI taxon_id.
    Local file I/O only — no network.
    """
    df = _normalize_columns(
        pd.read_csv(path, sep="\t", dtype=str, keep_default_na=False, na_values=["", "NA", "N/A"])
    )
    missing = REQUIRED_FLATFILE_COLUMNS - set(df.columns)
    if missing:
        raise FlatFileFormatError(
            f"{path} is missing required columns: {sorted(missing)}. This may indicate a "
            "BV-BRC schema change or the wrong filename — verify against "
            "Documentation/research-findings/bv-brc-data-access.md before proceeding."
        )
    if taxon_id is not None:
        df = df[df["taxon_id"].astype(str) == str(taxon_id)].reset_index(drop=True)
    return df


def parse_mlst(raw: object) -> tuple[str | None, int | None]:
    """Split a BV-BRC ``mlst`` value such as ``"kpneumoniae.258"`` into
    ``(scheme, sequence_type)``.

    Returns ``(None, None)`` when absent or in an unexpected format — defensive
    against MLST coverage/format surprises. ADR-0005's Mash fallback (EPIC 3) covers
    genomes without a usable sequence type; this function only needs to fail safe.
    """
    if raw is None:
        return None, None
    text = str(raw).strip()
    if not text or text.lower() in {"nan", "none", "-"}:
        return None, None
    match = _MLST_RE.match(text)
    if not match:
        return None, None
    scheme, sequence_type = match.groups()
    return scheme, int(sequence_type)


def parse_genome_metadata(
    path: Path, *, taxon_id: int | None = KLEBSIELLA_PNEUMONIAE_TAXON_ID
) -> pd.DataFrame:
    """Read the BV-BRC genome_metadata flat file and split ``mlst`` into
    ``mlst_scheme``/``mlst_st`` (see :func:`parse_mlst`). Local file I/O only."""
    df = _normalize_columns(
        pd.read_csv(path, sep="\t", dtype=str, keep_default_na=False, na_values=["", "NA", "N/A"])
    )
    missing = REQUIRED_METADATA_COLUMNS - set(df.columns)
    if missing:
        raise FlatFileFormatError(f"{path} is missing required columns: {sorted(missing)}")
    if taxon_id is not None:
        df = df[df["taxon_id"].astype(str) == str(taxon_id)].reset_index(drop=True)
    if "mlst" in df.columns:
        parsed = df["mlst"].map(parse_mlst)
        df["mlst_scheme"] = parsed.map(lambda t: t[0])
        df["mlst_st"] = parsed.map(lambda t: t[1])
    else:
        df["mlst_scheme"] = None
        df["mlst_st"] = None
    return df


# ---------------------------------------------------------------------------
# Evidence enumeration & filtering (issue #12 — the human checkpoint)
# ---------------------------------------------------------------------------


def _value_counts_with_blank(series: pd.Series) -> pd.Series:
    """``value_counts()`` after mapping NaN to a literal ``"<blank>"`` bucket, so
    missing values are visible in vocabulary enumerations rather than silently
    excluded."""
    return series.fillna("<blank>").value_counts()


def enumerate_evidence_values(df: pd.DataFrame) -> pd.Series:
    """Value counts of the raw ``evidence`` column across ALL rows, before any
    filtering.

    Run this before finalizing :func:`filter_lab_ast`'s ``evidence_values`` — never
    hardcode the lab-evidence filter without seeing what's actually present (issue
    #12; the research ground-truth observed only 2 values but BV-BRC's own docs
    describe up to 4).
    """
    return _value_counts_with_blank(df["evidence"])


def enumerate_sir_values(df: pd.DataFrame) -> pd.Series:
    """Value counts of the raw ``resistant_phenotype`` column (pre-canonicalization) —
    surfaces every literal SIR string actually present, including legacy
    abbreviations, so :data:`_SIR_ALIASES` can be checked against reality."""
    return _value_counts_with_blank(df["resistant_phenotype"])


def filter_lab_ast(
    df: pd.DataFrame,
    *,
    evidence_values: Collection[str] = (LAB_EVIDENCE,),
    require_typing_method: bool = True,
) -> pd.DataFrame:
    """Keep rows whose ``evidence`` is in ``evidence_values`` (default: lab-only, per
    ADR-0001) and, optionally, that have a non-empty ``laboratory_typing_method``.

    ``evidence_values`` is a parameter, not a hardcoded constant, so a newly
    enumerated lab-like value (e.g. an ``"AMR Panel"`` variant) can widen the filter
    via config once reviewed — never by silently changing this function.
    """
    mask = df["evidence"].isin(evidence_values)
    if require_typing_method:
        mask &= df["laboratory_typing_method"].fillna("").str.strip().ne("")
    return df.loc[mask].reset_index(drop=True)


# ---------------------------------------------------------------------------
# Canonicalization
# ---------------------------------------------------------------------------


def canonicalize_sir(raw: object) -> str | None:
    """Map one raw ``resistant_phenotype`` value onto a :data:`SIR_CLASSES` member,
    tolerating case, whitespace, and known legacy abbreviations (``Sensitive``/``S``
    -> Susceptible, ``I`` -> Intermediate, ``Non-susceptible`` -> Nonsusceptible,
    ``SDD`` -> Susceptible-dose dependent). Returns None if blank/unrecognized —
    multi-class, not binary; the binary S-vs-R collapse is EPIC 3's job.
    """
    if raw is None:
        return None
    text = str(raw).strip()
    if not text or text.lower() in {"nan", "none"}:
        return None
    return _SIR_ALIASES.get(text.lower())


def canonicalize_sir_series(series: pd.Series) -> pd.Series:
    """Vectorized :func:`canonicalize_sir` over a pandas Series."""
    return series.map(canonicalize_sir)


def canonicalize_antibiotic(name: object) -> str:
    """Lowercase/strip a raw antibiotic name and map known synonyms
    (:data:`_ANTIBIOTIC_ALIASES`) onto one canonical token, so per-drug counts and
    joins to ``constants.SUPPORTED_ANTIBIOTICS`` are stable. Unrecognized names pass
    through lowercased/stripped — every antibiotic is kept, not just the MVP panel.
    """
    return _ANTIBIOTIC_ALIASES.get(str(name).strip().lower(), str(name).strip().lower())


def attach_canonical_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Add canonical ``antibiotic`` and ``sir`` columns without collapsing
    duplicates — the shared first step for both the Phase-A count report (issue
    #12) and Phase-B label building (:func:`build_labels_bundle`).
    """
    out = df.copy()
    out["antibiotic"] = out["antibiotic"].map(canonicalize_antibiotic)
    out["sir"] = canonicalize_sir_series(out["resistant_phenotype"])
    return out


# ---------------------------------------------------------------------------
# Duplicate resolution & per-drug reporting
# ---------------------------------------------------------------------------


def resolve_duplicate_labels(
    df: pd.DataFrame,
    *,
    group_keys: tuple[str, str] = ("genome_id", "antibiotic"),
    sir_column: str = "sir",
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Collapse multiple lab-AST rows per (genome_id, antibiotic) to one SIR call by
    majority vote over the canonical SIR class.

    Two situations are treated as genuine, unresolvable contradictions and DROPPED
    rather than guessed at -- never train on contradictory ground truth:

    1. A class from ``_SUSCEPTIBLE_SIDE`` (Susceptible, Susceptible-dose dependent)
       and a class from ``_RESISTANT_SIDE`` (Resistant, Nonsusceptible) both appear
       anywhere in the group. Checked regardless of vote counts -- a 3-Resistant/
       1-Susceptible group is still a real disagreement, not a clean majority,
       because the two sides are clinical opposites (unlike e.g. Resistant+
       Intermediate, which does not contradict as sharply and resolves normally).
    2. More than one class ties for the top vote count (e.g. one Intermediate row
       and one Susceptible-dose-dependent row, no clear plurality).

    Rows with no canonical ``sir`` (already None) are excluded before voting.

    Returns ``(resolved, dropped)``: ``resolved`` has one row per group with
    ``sir_source_rows``/``sir_n_agree``/``sir_majority_fraction`` attached;
    ``dropped`` holds every row from a dropped (contradictory/tied) group, for the
    manifest's dropped-conflict count.
    """
    votable = df.dropna(subset=[sir_column]).copy()
    group_key_list = list(group_keys)
    resolved_rows: list[dict[str, object]] = []
    dropped_frames: list[pd.DataFrame] = []
    for key_values, group in votable.groupby(group_key_list, sort=False):
        keys = key_values if isinstance(key_values, tuple) else (key_values,)
        classes_present = set(group[sir_column])
        if classes_present & _SUSCEPTIBLE_SIDE and classes_present & _RESISTANT_SIDE:
            dropped_frames.append(group)
            continue
        counts = group[sir_column].value_counts()
        top_count = int(counts.iloc[0])
        winners = counts.index[counts == top_count]
        if len(winners) > 1:
            dropped_frames.append(group)
            continue
        row: dict[str, object] = dict(zip(group_key_list, keys, strict=True))
        row[sir_column] = str(winners[0])
        row["sir_source_rows"] = len(group)
        row["sir_n_agree"] = top_count
        row["sir_majority_fraction"] = top_count / len(group)
        resolved_rows.append(row)
    resolved = pd.DataFrame(resolved_rows)
    dropped = (
        pd.concat(dropped_frames, ignore_index=True) if dropped_frames else votable.iloc[0:0].copy()
    )
    return resolved, dropped


def per_drug_label_counts(df: pd.DataFrame, *, sir_column: str = "sir") -> pd.DataFrame:
    """Per antibiotic: row counts for each SIR class (0 if absent), total rows, and
    the number of DISTINCT genomes (rows overstate genome counts — one genome tested
    against one drug multiple times contributes multiple rows).

    This is the issue #12 report: it makes the min-n / panel-swap decision (e.g.
    ceftriaxone -> cefotaxime/ceftazidime) a plain reading of a table, not a guess.
    """
    rows: list[dict[str, object]] = []
    for antibiotic, group in df.groupby("antibiotic", sort=False):
        counts = group[sir_column].value_counts()
        row: dict[str, object] = {"antibiotic": antibiotic}
        for sir_class in SIR_CLASSES:
            row[sir_class] = int(counts.get(sir_class, 0))
        row["total"] = len(group)
        row["n_unique_genomes"] = int(group["genome_id"].nunique())
        rows.append(row)
    result = pd.DataFrame(rows)
    if result.empty:
        return result
    return result.sort_values("total", ascending=False, ignore_index=True)


def per_drug_standard_breakdown(df: pd.DataFrame) -> pd.DataFrame:
    """Per antibiotic: how many lab rows cite each ``testing_standard``
    (CLSI/EUCAST/other-or-blank) — surfaces the breakpoint-mixing risk documented in
    ADR-0001 (CLSI vs EUCAST can flip an SIR call for the same MIC).
    """
    rows: list[dict[str, object]] = []
    for antibiotic, group in df.groupby("antibiotic", sort=False):
        standard = group["testing_standard"].fillna("").str.strip().str.upper()
        rows.append(
            {
                "antibiotic": antibiotic,
                "clsi": int((standard == "CLSI").sum()),
                "eucast": int((standard == "EUCAST").sum()),
                "other_or_blank": int((~standard.isin({"CLSI", "EUCAST"})).sum()),
            }
        )
    result = pd.DataFrame(rows)
    if result.empty:
        return result
    return result.sort_values("antibiotic", ignore_index=True)


# ---------------------------------------------------------------------------
# MIC / provenance aggregation & final labels table
# ---------------------------------------------------------------------------


def _most_common(series: pd.Series) -> str | None:
    """Most frequent non-null value in ``series``, or None if it's empty. Ties break
    on the value itself (ascending) for determinism -- ``value_counts()`` alone does
    not guarantee a stable order across equal counts."""
    if series.empty:
        return None
    counts = series.value_counts()
    top = counts[counts == counts.iloc[0]]
    return str(sorted(top.index)[0])


def _parse_mic_sign(measurement: object) -> str | None:
    """Extract a leading comparator (``<=``, ``>=``, ``<``, ``>``, ``=``) from a raw
    ``measurement`` string such as ``"<=0.25"``; None if absent/unparseable."""
    if measurement is None:
        return None
    match = _MIC_SIGN_RE.match(str(measurement))
    return match.group(1) if match else None


def _aggregate_mic(df: pd.DataFrame) -> pd.DataFrame:
    """One row per (genome_id, antibiotic): median MIC value and its sign, restricted
    to the single most common ``measurement_unit`` in the group.

    Different lab methods report incompatible measurement types under the same
    ``measurement_value`` column -- e.g. broth-dilution MIC in mg/L vs disk-diffusion
    zone diameter in mm. Blending them into one median would fabricate a number that
    describes neither. Restricting to the dominant unit keeps ``mic_value``,
    ``mic_sign``, and ``mic_unit`` mutually consistent, drawn from the same rows.
    """
    rows: list[dict[str, object]] = []
    for (genome_id, antibiotic), group in df.groupby(["genome_id", "antibiotic"], sort=False):
        units = group["measurement_unit"].fillna("").str.strip()
        units = units[units != ""]
        # On a genuine tie (e.g. one "mm" row and one "mg/L" row), _most_common's
        # alphabetical tie-break picks a unit arbitrarily -- acceptable because
        # mic_unit always names whichever unit won, so mic_value is never mislabeled.
        dominant_unit = _most_common(units)
        if dominant_unit is None:
            rows.append(
                {
                    "genome_id": genome_id,
                    "antibiotic": antibiotic,
                    "mic_value": None,
                    "mic_sign": None,
                    "mic_unit": None,
                }
            )
            continue
        same_unit = group[group["measurement_unit"].fillna("").str.strip() == dominant_unit]
        values = pd.to_numeric(same_unit["measurement_value"], errors="coerce").dropna()
        signs = same_unit["measurement"].map(_parse_mic_sign).dropna()
        rows.append(
            {
                "genome_id": genome_id,
                "antibiotic": antibiotic,
                "mic_value": float(values.median()) if not values.empty else None,
                "mic_sign": _most_common(signs),
                "mic_unit": dominant_unit,
            }
        )
    return pd.DataFrame(rows)


def _aggregate_provenance(df: pd.DataFrame) -> pd.DataFrame:
    """One row per (genome_id, antibiotic): dominant ``testing_standard``, the
    ``testing_standard_year`` span, and every distinct lab typing method observed."""
    rows: list[dict[str, object]] = []
    for (genome_id, antibiotic), group in df.groupby(["genome_id", "antibiotic"], sort=False):
        standards = group["testing_standard"].fillna("").str.strip()
        standards = standards[standards != ""]
        years = pd.to_numeric(group["testing_standard_year"], errors="coerce").dropna()
        methods = sorted(
            {m.strip() for m in group["laboratory_typing_method"].dropna() if m.strip()}
        )
        rows.append(
            {
                "genome_id": genome_id,
                "antibiotic": antibiotic,
                "dominant_testing_standard": _most_common(standards) or "",
                "testing_standard_year_min": int(years.min()) if not years.empty else None,
                "testing_standard_year_max": int(years.max()) if not years.empty else None,
                "lab_typing_methods": ";".join(methods),
            }
        )
    return pd.DataFrame(rows)


class LabelsBuildResult(NamedTuple):
    """Everything :func:`build_manifest` needs from one dataset build, alongside the
    final table."""

    labels: pd.DataFrame
    dropped_conflicts: pd.DataFrame
    working: pd.DataFrame
    """lab_rows with canonical antibiotic/sir columns attached, pre-collapse."""


def build_labels_bundle(lab_rows: pd.DataFrame) -> LabelsBuildResult:
    """Canonicalize, collapse duplicates, and attach MIC/provenance.

    Returns the final labels table plus the intermediates (dropped conflicts,
    canonicalized pre-collapse rows) that :func:`build_manifest` needs for its counts.
    3-class SIR is kept throughout — the binary drop-Intermediate collapse for
    training is EPIC 3's responsibility.
    """
    working = attach_canonical_columns(lab_rows)
    resolved, dropped = resolve_duplicate_labels(working)
    mic_by_pair = _aggregate_mic(working)
    provenance_by_pair = _aggregate_provenance(working)
    labels = (
        resolved.merge(mic_by_pair, on=["genome_id", "antibiotic"], how="left")
        .merge(provenance_by_pair, on=["genome_id", "antibiotic"], how="left")
        .sort_values(["antibiotic", "genome_id"], ignore_index=True)
        .reindex(columns=list(LABELS_COLUMNS_CORE))
    )
    return LabelsBuildResult(labels=labels, dropped_conflicts=dropped, working=working)


def build_labels_table(lab_rows: pd.DataFrame) -> pd.DataFrame:
    """Convenience wrapper around :func:`build_labels_bundle` for callers that only
    need the final table (e.g. most tests, and simple scripting)."""
    return build_labels_bundle(lab_rows).labels


def mark_fasta_availability(
    labels: pd.DataFrame, genome_ids_with_fasta: Collection[str]
) -> pd.DataFrame:
    """Attach a boolean ``has_fasta`` column marking which genome_ids have a locally
    downloaded ``.fna`` (the set is produced by scripts/build_dataset.py from a
    directory listing — this function itself does no filesystem I/O)."""
    out = labels.copy()
    available = set(genome_ids_with_fasta)
    out["has_fasta"] = out["genome_id"].isin(available)
    return out


def select_genome_ids(
    labels: pd.DataFrame,
    *,
    antibiotics: Collection[str] | None = None,
    min_n_per_drug: int | None = None,
) -> list[str]:
    """Deduplicated, sorted genome_id list to hand to Phase-B FASTA download:
    optionally restricted to a finalized antibiotic panel and/or drugs meeting a
    min-n label count. Pure — this IS the human-checkpoint -> Phase-B boundary.
    """
    working = labels
    if antibiotics is not None:
        working = working[working["antibiotic"].isin(antibiotics)]
    if min_n_per_drug is not None:
        counts = working.groupby("antibiotic")["genome_id"].transform("count")
        working = working[counts >= min_n_per_drug]
    return sorted(working["genome_id"].dropna().unique().tolist())


def validate_labels_schema(df: pd.DataFrame) -> None:
    """Assert ``df`` matches the labels.parquet column contract: LABELS_COLUMNS are
    all present and every non-null ``sir`` value is a canonical SIR_CLASSES member.

    Raises AssertionError on violation. This is the cheap substitute for per-row
    Pydantic validation on an 85k-row table (see module docstring); it checks the
    column *contract* and label vocabulary, not exact dtypes.
    """
    missing = set(LABELS_COLUMNS) - set(df.columns)
    if missing:
        raise AssertionError(f"labels table missing columns: {sorted(missing)}")
    bad_sir = set(df["sir"].dropna().unique()) - set(SIR_CLASSES)
    if bad_sir:
        raise AssertionError(f"labels table has non-canonical sir values: {sorted(bad_sir)}")


# ---------------------------------------------------------------------------
# Provenance manifest
# ---------------------------------------------------------------------------


class BvbrcSourceInfo(BaseModel):
    """Where the raw data came from — the download-side half of the manifest."""

    model_config = ConfigDict(extra="forbid")

    ftps_host: str
    amr_flatfile: str
    genome_metadata_file: str | None = None
    download_utc: str | None = None


class PerDrugManifestEntry(BaseModel):
    """One antibiotic's row from the issue #12 count report, frozen into the
    manifest."""

    model_config = ConfigDict(extra="forbid")

    antibiotic: str
    resistant: int
    susceptible: int
    intermediate: int
    nonsusceptible: int
    susceptible_dose_dependent: int
    total: int
    n_unique_genomes: int
    clsi: int
    eucast: int
    other_or_blank_standard: int
    dropped_conflict: int


class MlstCoverage(BaseModel):
    """How much of the genome set has a usable MLST sequence type — scopes EPIC 3's
    ADR-0005 Mash fallback."""

    model_config = ConfigDict(extra="forbid")

    genomes_total: int
    with_st: int
    missing_st: int
    missing_fraction: float


class DatasetCounts(BaseModel):
    """Row/genome counts at each pipeline stage."""

    model_config = ConfigDict(extra="forbid")

    raw_rows: int
    lab_rows: int
    labels_after_collapse: int
    dropped_conflict: int
    dropped_uncanonical_sir: int
    unique_genomes: int
    genomes_with_fasta: int


class DatasetManifest(BaseModel):
    """Provenance record for one EPIC 1 dataset build.

    Every filter, count, and vocabulary the labels/genome_metadata parquet files were
    built from — written to data/processed/dataset_manifest.json (see PRD Artifacts).
    The one Pydantic model in this module; see the module docstring for why.
    """

    model_config = ConfigDict(extra="forbid")

    created_utc: str
    taxon_id: int
    source: BvbrcSourceInfo
    evidence_values_kept: tuple[str, ...]
    require_typing_method: bool
    evidence_vocabulary: dict[str, int]
    sir_vocabulary_raw: dict[str, int]
    counts: DatasetCounts
    per_drug: tuple[PerDrugManifestEntry, ...]
    mlst: MlstCoverage
    panel_selected: tuple[str, ...] = ()
    download_cap: int | None = None
    tool_versions: dict[str, str] = Field(default_factory=dict)


def build_manifest(
    *,
    labels: pd.DataFrame,
    working: pd.DataFrame,
    dropped_conflicts: pd.DataFrame,
    raw_rows: pd.DataFrame,
    lab_rows: pd.DataFrame,
    genome_metadata: pd.DataFrame | None,
    per_drug: pd.DataFrame,
    standard_breakdown: pd.DataFrame,
    evidence_counts: pd.Series,
    sir_counts_raw: pd.Series,
    source: BvbrcSourceInfo,
    taxon_id: int = KLEBSIELLA_PNEUMONIAE_TAXON_ID,
    evidence_values_kept: Collection[str] = (LAB_EVIDENCE,),
    require_typing_method: bool = True,
    panel_selected: Collection[str] = (),
    download_cap: int | None = None,
    created_utc: str | None = None,
) -> DatasetManifest:
    """Assemble the typed provenance manifest from the intermediate tables produced
    while building the dataset.

    Pure — callers (scripts/build_dataset.py) supply every input; this function does
    no I/O. ``working`` is the pre-collapse frame with canonical antibiotic/sir
    columns (see :class:`LabelsBuildResult`); ``per_drug``/``standard_breakdown`` are
    computed by :func:`per_drug_label_counts`/:func:`per_drug_standard_breakdown` on
    that same ``working`` frame so the manifest matches the issue #12 report exactly.
    """
    per_drug_by_antibiotic = per_drug.set_index("antibiotic") if not per_drug.empty else per_drug
    standard_by_antibiotic = (
        standard_breakdown.set_index("antibiotic")
        if not standard_breakdown.empty
        else standard_breakdown
    )
    dropped_by_antibiotic = (
        dropped_conflicts.groupby("antibiotic").size()
        if not dropped_conflicts.empty
        else pd.Series(dtype=int)
    )

    entries: list[PerDrugManifestEntry] = []
    for antibiotic_key, row in per_drug_by_antibiotic.iterrows():
        # .to_dict() turns pandas-stubs' ambiguous Series.__getitem__ overloads (which
        # can resolve to `Any | Series[Any]`) into plain `Any` values int() accepts.
        antibiotic = str(antibiotic_key)
        values = row.to_dict()
        has_std = (
            antibiotic in standard_by_antibiotic.index
            if not standard_by_antibiotic.empty
            else False
        )
        std_values = standard_by_antibiotic.loc[antibiotic].to_dict() if has_std else None
        entries.append(
            PerDrugManifestEntry(
                antibiotic=antibiotic,
                resistant=int(values["Resistant"]),
                susceptible=int(values["Susceptible"]),
                intermediate=int(values["Intermediate"]),
                nonsusceptible=int(values["Nonsusceptible"]),
                susceptible_dose_dependent=int(values["Susceptible-dose dependent"]),
                total=int(values["total"]),
                n_unique_genomes=int(values["n_unique_genomes"]),
                clsi=int(std_values["clsi"]) if std_values is not None else 0,
                eucast=int(std_values["eucast"]) if std_values is not None else 0,
                other_or_blank_standard=int(std_values["other_or_blank"])
                if std_values is not None
                else 0,
                dropped_conflict=int(dropped_by_antibiotic.get(antibiotic, 0)),
            )
        )

    genomes_total = len(genome_metadata) if genome_metadata is not None else 0
    with_st = (
        int(genome_metadata["mlst_st"].notna().sum())
        if genome_metadata is not None and "mlst_st" in genome_metadata.columns
        else 0
    )
    missing_st = genomes_total - with_st
    mlst = MlstCoverage(
        genomes_total=genomes_total,
        with_st=with_st,
        missing_st=missing_st,
        missing_fraction=(missing_st / genomes_total) if genomes_total else 0.0,
    )

    counts = DatasetCounts(
        raw_rows=len(raw_rows),
        lab_rows=len(lab_rows),
        labels_after_collapse=len(labels),
        dropped_conflict=len(dropped_conflicts),
        dropped_uncanonical_sir=len(working[working["sir"].isna()]),
        unique_genomes=len(labels["genome_id"].unique()),
        genomes_with_fasta=len(labels[labels["has_fasta"]]) if "has_fasta" in labels.columns else 0,
    )

    return DatasetManifest(
        created_utc=created_utc or datetime.now(UTC).isoformat(),
        taxon_id=taxon_id,
        source=source,
        evidence_values_kept=tuple(evidence_values_kept),
        require_typing_method=require_typing_method,
        evidence_vocabulary={str(k): int(v) for k, v in evidence_counts.items()},
        sir_vocabulary_raw={str(k): int(v) for k, v in sir_counts_raw.items()},
        counts=counts,
        per_drug=tuple(entries),
        mlst=mlst,
        panel_selected=tuple(panel_selected),
        download_cap=download_cap,
        tool_versions={"python": platform.python_version(), "pandas": pd.__version__},
    )
