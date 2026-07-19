"""Feature vocabulary + engineered combination features (the reader -> predictor bridge).

build_vocabulary freezes the ordered, hashed feature list a per-drug model trains on: every
gene-presence symbol and point-mutation seen across the training cohort, then the fixed
engineered combination columns the literature says the fluoroquinolone and aminoglycoside
classes need (antibiotic-panel.md: mutation COUNTS + PMQR/RMTase presence, not flat
one-hot). Pure and LLM-free.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable

from genome_firewall.features import mechanisms
from genome_firewall.reader.feature_builder import SCHEMA_VERSION
from genome_firewall.schemas import GenomeFeatureVector, ModelFeatureSchema

#: Bump when engineered_features changes (added/removed/renamed column, changed formula);
#: stamped into every ModelFeatureSchema so predict.py rejects a genome built under a
#: different engineered-feature contract (issue #22).
ENGINEERED_SPEC_VERSION = "1"

#: Namespace prefix so an engineered column can never collide with a real gene/mutation
#: symbol (which never contains a colon).
ENGINEERED_PREFIX = "eng:"

_ENGINEERED_BASE_NAMES: tuple[str, ...] = (
    "n_qrdr_mutations",
    "has_pmqr",
    "has_rmtase",
    "has_ame",
    "has_carbapenemase",
    "has_esbl_or_ampc",
    "has_sul",
    "has_dfr",
    "porin_disrupted",
)
ENGINEERED_FEATURE_NAMES: tuple[str, ...] = tuple(
    f"{ENGINEERED_PREFIX}{name}" for name in _ENGINEERED_BASE_NAMES
)


def engineered_features(vector: GenomeFeatureVector) -> dict[str, float]:
    """Deterministic combination features from the raw gene/mutation calls (bare names, no
    ENGINEERED_PREFIX). Counts/booleans-as-floats so they slot straight into a numeric row.
    """
    return {
        "n_qrdr_mutations": float(len(mechanisms.qrdr_mutations(vector))),
        "has_pmqr": float(bool(mechanisms.pmqr_hits(vector))),
        "has_rmtase": float(bool(mechanisms.rmtase_hits(vector))),
        "has_ame": float(bool(mechanisms.ame_hits(vector))),
        "has_carbapenemase": float(bool(mechanisms.carbapenemase_hits(vector))),
        "has_esbl_or_ampc": float(bool(mechanisms.esbl_ampc_hits(vector))),
        "has_sul": float(bool(mechanisms.sul_hits(vector))),
        "has_dfr": float(bool(mechanisms.dfr_hits(vector))),
        "porin_disrupted": float(bool(mechanisms.porin_disruptions(vector))),
    }


def build_vocabulary(
    vectors: Iterable[GenomeFeatureVector],
    *,
    amrfinder_db_version: str,
    schema_version: str = SCHEMA_VERSION,
) -> ModelFeatureSchema:
    """Freeze the ordered feature vocabulary over a training cohort: sorted gene-presence
    symbols, then sorted point-mutation symbols (minus any that collide with a gene name),
    then the fixed engineered columns. Column order IS the model's coefficient order; the
    SHA-256 pins exact identity.
    """
    genes: set[str] = set()
    mutations: set[str] = set()
    for vector in vectors:
        genes.update(vector.gene_presence)
        mutations.update(vector.point_mutations)
    feature_names = (*sorted(genes), *sorted(mutations - genes), *ENGINEERED_FEATURE_NAMES)
    digest = hashlib.sha256("\n".join(feature_names).encode("utf-8")).hexdigest()
    return ModelFeatureSchema(
        schema_version=schema_version,
        amrfinder_db_version=amrfinder_db_version,
        engineered_feature_spec_version=ENGINEERED_SPEC_VERSION,
        feature_names=feature_names,
        vocabulary_sha256=digest,
    )
