"""Capped, stratified genome-subset selection for the EPIC 3 real training run (issue #18).

Pure, network-free. The full BV-BRC K. pneumoniae lab-AST set is far larger than a
few-hour AMRFinderPlus batch can annotate; this picks a bounded subset that still clears
the per-drug min-n gate for as many panel drugs as possible, while capping any single
MLST ST's share so the homology-aware grouped split (ADR-0005) keeps enough distinct
groups to stratify over -- a subset dominated by one clone (e.g. ST258) would collapse
StratifiedGroupKFold toward GroupKFold. The realized composition is returned as a
:class:`SubsetSelection` for the dataset manifest: the cap and selection rule are
recorded, never silently applied (no silent truncation).

Must not import genome_firewall.llm (enforced by scripts/check_import_boundary.py).
"""

from __future__ import annotations

from collections.abc import Collection

import pandas as pd
from pydantic import BaseModel, ConfigDict

from genome_firewall.constants import (
    MIN_RESISTANT_PER_DRUG,
    MIN_SUSCEPTIBLE_PER_DRUG,
    SUPPORTED_ANTIBIOTICS,
)
from genome_firewall.predictor.dataset import collapse_sir_to_binary, mlst_group_id

#: Default per-(drug, side) genome quota: ~2x the min-n gate so a calibration/conformal
#: fold survives after the grouped split leaves a test fold aside.
_DEFAULT_PER_DRUG_TARGET: int = 2 * max(MIN_RESISTANT_PER_DRUG, MIN_SUSCEPTIBLE_PER_DRUG)


class SubsetSelection(BaseModel):
    """The realized composition of one capped, stratified genome subset -- recorded in the
    dataset manifest so the cap and selection rule stay auditable."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    cap: int
    per_drug_target: int
    max_per_st_fraction: float
    genome_ids: tuple[str, ...]
    n_selected: int
    n_distinct_groups: int
    #: "<drug>|R"/"<drug>|S" -> count of selected genomes carrying that labelled cell.
    per_cell_counts: dict[str, int]
    #: homology group id -> count of selected genomes in it (the ST-cap audit trail).
    per_group_counts: dict[str, int]
    drugs_meeting_target: tuple[str, ...]
    drugs_below_target: tuple[str, ...]


def select_capped_stratified_subset(
    labels: pd.DataFrame,
    metadata: pd.DataFrame,
    *,
    cap: int,
    antibiotics: Collection[str] = SUPPORTED_ANTIBIOTICS,
    per_drug_target: int = _DEFAULT_PER_DRUG_TARGET,
    max_per_st_fraction: float = 0.15,
) -> SubsetSelection:
    """Greedily pick <= ``cap`` genome_ids that fill each panel drug's R/S quota while
    capping any one MLST group to ``max_per_st_fraction`` of the cap.

    Deterministic: candidate genomes are considered in sorted genome_id order and ties are
    broken by genome_id, so the same inputs always yield the same subset. Phase 1 fills the
    per-(drug, side) quotas; phase 2 spends any remaining budget on genomes from the
    least-represented groups (diversity), never exceeding the cap or a group's ST cap.
    """
    if cap <= 0:
        raise ValueError("cap must be positive")
    panel = tuple(antibiotics)
    st_cap = max(1, int(max_per_st_fraction * cap))

    binary = collapse_sir_to_binary(labels)
    binary = binary[binary["antibiotic"].isin(panel)]

    # genome_id -> {"<drug>|<side>", ...}
    cells_by_genome: dict[str, set[str]] = {}
    for gid, drug, side in zip(
        binary["genome_id"].astype(str).tolist(),
        binary["antibiotic"].astype(str).tolist(),
        binary["sir_binary"].astype(str).tolist(),
        strict=True,
    ):
        cells_by_genome.setdefault(gid, set()).add(f"{drug}|{side}")

    # genome_id -> homology group id, seeded from metadata (missing -> singleton).
    group_by_genome: dict[str, str] = {}
    meta = metadata.reset_index(drop=True)
    if "genome_id" in meta.columns:
        gids = meta["genome_id"].astype(str).tolist()
        n = len(gids)
        schemes = meta["mlst_scheme"].tolist() if "mlst_scheme" in meta.columns else [None] * n
        sts = meta["mlst_st"].tolist() if "mlst_st" in meta.columns else [None] * n
        for gid, scheme, st in zip(gids, schemes, sts, strict=True):
            group_by_genome.setdefault(gid, mlst_group_id(scheme, st, gid))

    def group_for(gid: str) -> str:
        group = group_by_genome.get(gid)
        if group is None:
            group = mlst_group_id(None, None, gid)
            group_by_genome[gid] = group
        return group

    candidates = sorted(cells_by_genome)
    filled: dict[str, int] = {cell: 0 for cells in cells_by_genome.values() for cell in cells}
    per_group: dict[str, int] = {}
    selected: set[str] = set()

    def take(gid: str) -> None:
        selected.add(gid)
        per_group[group_for(gid)] = per_group.get(group_for(gid), 0) + 1
        for cell in cells_by_genome[gid]:
            filled[cell] += 1

    # Phase 1: fill per-(drug, side) quotas, picking the genome that closes the most still-
    # open cells each round (ties -> lowest genome_id via the sorted candidate scan).
    while len(selected) < cap:
        best_gid: str | None = None
        best_score = 0
        for gid in candidates:
            if gid in selected or per_group.get(group_for(gid), 0) >= st_cap:
                continue
            score = sum(1 for cell in cells_by_genome[gid] if filled[cell] < per_drug_target)
            if score > best_score:
                best_score = score
                best_gid = gid
        if best_gid is None or best_score == 0:
            break
        take(best_gid)

    # Phase 2: diversity top-up to the cap -- prefer genomes in the least-represented groups.
    if len(selected) < cap:
        remaining = sorted(
            (gid for gid in candidates if gid not in selected),
            key=lambda gid: (per_group.get(group_for(gid), 0), gid),
        )
        for gid in remaining:
            if len(selected) >= cap:
                break
            if per_group.get(group_for(gid), 0) >= st_cap:
                continue
            take(gid)

    drugs_meeting: list[str] = []
    drugs_below: list[str] = []
    for drug in panel:
        r = filled.get(f"{drug}|R", 0)
        s = filled.get(f"{drug}|S", 0)
        if r >= per_drug_target and s >= per_drug_target:
            drugs_meeting.append(drug)
        else:
            drugs_below.append(drug)

    return SubsetSelection(
        cap=cap,
        per_drug_target=per_drug_target,
        max_per_st_fraction=max_per_st_fraction,
        genome_ids=tuple(sorted(selected)),
        n_selected=len(selected),
        n_distinct_groups=len(per_group),
        per_cell_counts={cell: filled[cell] for cell in sorted(filled)},
        per_group_counts={group: per_group[group] for group in sorted(per_group)},
        drugs_meeting_target=tuple(drugs_meeting),
        drugs_below_target=tuple(drugs_below),
    )
