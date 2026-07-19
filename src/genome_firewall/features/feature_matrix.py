"""Map GenomeFeatureVector -> fixed-order numeric rows against a frozen ModelFeatureSchema.

Pure, LLM-free. A gene/mutation the schema knows but the genome lacks -> 0.0; a gene the
genome carries but the schema does NOT know -> dropped as out-of-vocabulary, its count
returned as an out-of-distribution signal (never an error here -- predict.py decides what a
schema/DB-version mismatch means; this layer is a pure numeric transform).
"""

from __future__ import annotations

from collections.abc import Iterable

import numpy as np
import numpy.typing as npt
import pandas as pd

from genome_firewall.features.vocabulary import ENGINEERED_PREFIX, engineered_features
from genome_firewall.schemas import GenomeFeatureVector, ModelFeatureSchema


def build_feature_row(
    vector: GenomeFeatureVector, schema: ModelFeatureSchema
) -> tuple[npt.NDArray[np.float64], int]:
    """One genome -> (numeric row aligned to schema.feature_names, out-of-vocabulary count)."""
    engineered = engineered_features(vector)
    values: list[float] = []
    for name in schema.feature_names:
        if name.startswith(ENGINEERED_PREFIX):
            values.append(engineered.get(name[len(ENGINEERED_PREFIX) :], 0.0))
        elif vector.gene_presence.get(name) or vector.point_mutations.get(name):
            values.append(1.0)
        else:
            values.append(0.0)
    known = set(schema.feature_names)
    oov = sum(1 for gene in vector.gene_presence if gene not in known)
    oov += sum(1 for mutation in vector.point_mutations if mutation not in known)
    return np.asarray(values, dtype=np.float64), oov


def assemble_feature_matrix(
    vectors: Iterable[GenomeFeatureVector], schema: ModelFeatureSchema
) -> pd.DataFrame:
    """Stack build_feature_row over a cohort into a genome_id-indexed DataFrame whose
    columns are exactly schema.feature_names (the training/inference matrix)."""
    columns = list(schema.feature_names)
    rows: dict[str, npt.NDArray[np.float64]] = {}
    for vector in vectors:
        row, _oov = build_feature_row(vector, schema)
        rows[vector.genome_id] = row
    matrix = pd.DataFrame.from_dict(rows, orient="index", columns=columns)
    matrix.index.name = "genome_id"
    return matrix
