"""Shared synthetic cohort for predictor tests -- a small labelled feature set with a KNOWN
resistance structure so split/train/calibration/gate are all testable offline (no Docker,
no network). Deterministic.

Structure (120 genomes across 24 MLST STs, 5 genomes each):
  * gentamicin  -- a MODEL drug: resistance driven by the AME aac(3)-IIa, which the gate does
    NOT fire on, so the calibrated model must learn it. ~72 R / 48 S.
  * meropenem   -- a GATE drug: resistance driven by the carbapenemase blaKPC-2 (the gate
    fires and short-circuits the model). 24 R / 96 S.
  * ciprofloxacin -- deliberately THIN (only 8 labelled genomes) so it fails the min-n gate.
Every ST carries a mix of classes (within-ST index, independent of ST) so the grouped split
does not degenerate.
"""

from __future__ import annotations

import pandas as pd
import pytest

from genome_firewall.schemas import GenomeFeatureVector

SyntheticCohort = tuple[list[GenomeFeatureVector], dict[str, dict[str, str]], pd.DataFrame]


def make_synthetic_cohort() -> SyntheticCohort:
    vectors: list[GenomeFeatureVector] = []
    labels: dict[str, dict[str, str]] = {"gentamicin": {}, "meropenem": {}, "ciprofloxacin": {}}
    meta_rows: list[tuple[str, str, str]] = []
    for i in range(120):
        gid = f"g{i:03d}"
        st = i // 5
        within = i % 5
        meta_rows.append((gid, "kpneumoniae", str(st)))

        gene_presence: dict[str, bool] = {"blaSHV-11": True}  # ubiquitous narrow-spectrum
        gene_drug_subclass: dict[str, str] = {"blaSHV-11": "BETA-LACTAM"}
        point_mutations: dict[str, bool] = {}

        gentamicin_resistant = within in (0, 1, 2)
        if gentamicin_resistant:
            gene_presence["aac(3)-IIa"] = True
            gene_drug_subclass["aac(3)-IIa"] = "GENTAMICIN"
        labels["gentamicin"][gid] = "R" if gentamicin_resistant else "S"

        meropenem_resistant = within == 0
        if meropenem_resistant:
            gene_presence["blaKPC-2"] = True
            gene_drug_subclass["blaKPC-2"] = "CARBAPENEM"
        labels["meropenem"][gid] = "R" if meropenem_resistant else "S"

        if i < 8:  # thin -> below the min-n gate
            cip_resistant = i < 3
            if cip_resistant:
                point_mutations["gyrA_S83Y"] = True
                point_mutations["parC_S80I"] = True
            labels["ciprofloxacin"][gid] = "R" if cip_resistant else "S"

        vectors.append(
            GenomeFeatureVector(
                genome_id=gid,
                schema_version="1.0.0",
                amrfinder_db_version="2026-05-15.1",
                gene_presence=gene_presence,
                gene_drug_subclass=gene_drug_subclass,
                point_mutations=point_mutations,
            )
        )
    metadata = pd.DataFrame(meta_rows, columns=["genome_id", "mlst_scheme", "mlst_st"])
    return vectors, labels, metadata


@pytest.fixture
def synthetic_cohort() -> SyntheticCohort:
    return make_synthetic_cohort()
