"""Shared AMRFinderPlus TSV -> AmrFeature parsing.

Used by BOTH the real Docker runner (amrfinder.py) and MockAnnotator (mock.py) so their
output is guaranteed structurally identical -- the one place mock-vs-real drift (ADR-0002's
to-validate item) can be fixed once instead of two parsers silently diverging.

Column names below are the REAL AMRFinderPlus TSV header, confirmed against a live
`ncbi/amr:4.2.7-2026-05-15.1` Docker run against a real K. pneumoniae genome -- not the
paraphrased column list in research-findings/amrfinderplus-features.md (that doc, written
before any real run, omitted the leading "Name" column and used "Element type"/"Element
subtype" where the real header just says "Type"/"Subtype").
"""

from __future__ import annotations

import csv
from pathlib import Path

from genome_firewall.schemas import AmrFeature

_NA = "NA"


def _na_to_none(value: str) -> str | None:
    return None if value == _NA else value


def parse_amrfinder_tsv(path: Path) -> tuple[AmrFeature, ...]:
    """Parse one `--name`-tagged AMRFinderPlus TSV report into AmrFeature rows.

    Uses `AmrFeature.model_validate` (not keyword construction) so an AMRFinderPlus
    value outside our closed Literal sets (e.g. a Method/Scope/Type the DB pin didn't
    exist yet when this was written) raises a clear pydantic.ValidationError instead of
    being silently miscategorized -- exactly the DB-version-drift failure mode
    research-findings/architecture.md's "Risks" section calls out.
    """
    with path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh, delimiter="\t")
        return tuple(_row_to_feature(row) for row in reader)


def _row_to_feature(row: dict[str, str]) -> AmrFeature:
    payload = {
        "gene_symbol": row["Element symbol"],
        "sequence_name": row["Element name"],
        "scope": row["Scope"],
        "element_type": row["Type"],
        "element_subtype": row["Subtype"],
        "drug_class": _na_to_none(row["Class"]),
        "drug_subclass": _na_to_none(row["Subclass"]),
        "method": row["Method"],
        "pct_coverage": float(row["% Coverage of reference"]),
        "pct_identity": float(row["% Identity to reference"]),
        "contig_id": row["Contig id"],
        "start": int(row["Start"]),
        "stop": int(row["Stop"]),
        "strand": row["Strand"],
        "closest_reference_accession": _na_to_none(row["Closest reference accession"]),
        "closest_reference_name": _na_to_none(row["Closest reference name"]),
    }
    return AmrFeature.model_validate(payload)
