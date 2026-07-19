"""Deterministic evidence assembly + KNOWN_MECHANISM / STATISTICAL_ASSOCIATION tagging.

Safety-critical (golden rule #3, ADR-0020). The tag is set by **deterministic KB-membership**
-- a supporting gene/mutation is ``known_mechanism`` iff it is a member of the curated
mechanism KB for that drug (``features/mechanisms.py``, the single source of truth also driving
the deterministic gate). A feature the *model* merely weighted is ``statistical_association``.
The LLM never sets this tag.

Row-level ``evidence_category`` is the strongest category among the cited items
(``known_mechanism`` > ``statistical_association`` > ``no_signal``). This satisfies the
``AntibioticPrediction`` validators by construction: a non-``no_signal`` row always carries
non-empty ``supporting_features``, and the row category is always backed by at least one cited
``EvidenceItem`` of that category.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from genome_firewall.features import mechanisms
from genome_firewall.predictor.dataset import canonicalize_antibiotic
from genome_firewall.schemas import EvidenceCategory, EvidenceItem, GenomeFeatureVector

_Extractor = Callable[[GenomeFeatureVector], tuple[str, ...]]


@dataclass(frozen=True)
class _MechanismSpec:
    """A curated known-mechanism family for a drug: how to detect its hits + how to describe."""

    extractor: _Extractor
    description: str


#: Per-drug curated known-mechanism families (keyed by canonical antibiotic). Anchored to the
#: exact predicates in features/mechanisms.py so evidence tagging and the gate never diverge.
_KNOWN_MECHANISMS: dict[str, tuple[_MechanismSpec, ...]] = {
    "meropenem": (
        _MechanismSpec(mechanisms.carbapenemase_hits, "carbapenemase hydrolysing carbapenems"),
        _MechanismSpec(
            mechanisms.porin_disruptions,
            "porin (ompK35/ompK36) disruption reducing carbapenem uptake",
        ),
    ),
    "ceftriaxone": (
        _MechanismSpec(
            mechanisms.cephalosporin_resistance_hits,
            "ESBL/AmpC or carbapenemase hydrolysing 3rd-generation cephalosporins",
        ),
    ),
    "ciprofloxacin": (
        _MechanismSpec(mechanisms.qrdr_mutations, "QRDR target-site mutation in gyrA/parC"),
        _MechanismSpec(mechanisms.pmqr_hits, "plasmid-mediated quinolone-resistance determinant"),
    ),
    "gentamicin": (
        _MechanismSpec(
            mechanisms.rmtase_hits,
            "16S rRNA methyltransferase (high-level pan-aminoglycoside resistance)",
        ),
        _MechanismSpec(mechanisms.ame_hits, "aminoglycoside-modifying enzyme"),
    ),
    "trimethoprim-sulfamethoxazole": (
        _MechanismSpec(mechanisms.sul_hits, "sulfonamide dihydropteroate-synthase bypass (sul)"),
        _MechanismSpec(mechanisms.dfr_hits, "trimethoprim dihydrofolate-reductase bypass (dfr)"),
    ),
}


@dataclass(frozen=True)
class EvidenceBundle:
    """Assembled evidence for one antibiotic row."""

    evidence: tuple[EvidenceItem, ...]
    supporting_features: tuple[str, ...]
    category: EvidenceCategory


def _citation(vector: GenomeFeatureVector, name: str) -> str:
    """A traceable source string for one hit (golden rule #3)."""
    if name in vector.gene_presence:
        subclass = vector.gene_drug_subclass.get(name, "unknown")
        return f"{name} (AMRFinderPlus Subclass={subclass})"
    return f"{name} (AMRFinderPlus point mutation)"


def known_mechanism_hits(antibiotic: str, vector: GenomeFeatureVector) -> tuple[str, ...]:
    """The ordered, de-duplicated curated known-mechanism gene/mutation names for this drug."""
    specs = _KNOWN_MECHANISMS.get(canonicalize_antibiotic(antibiotic), ())
    seen: dict[str, None] = {}
    for spec in specs:
        for name in spec.extractor(vector):
            seen.setdefault(name, None)
    return tuple(seen)


def _known_items(
    antibiotic: str, vector: GenomeFeatureVector
) -> tuple[tuple[str, EvidenceItem], ...]:
    specs = _KNOWN_MECHANISMS.get(canonicalize_antibiotic(antibiotic), ())
    out: dict[str, EvidenceItem] = {}
    for spec in specs:
        for name in spec.extractor(vector):
            if name in out:
                continue
            out[name] = EvidenceItem(
                description=f"{name}: {spec.description}",
                source=_citation(vector, name),
                evidence_category="known_mechanism",
            )
    return tuple(out.items())


def _statistical_items(
    model_top_features: tuple[str, ...],
    known_names: frozenset[str],
    model_version: str,
) -> tuple[tuple[str, EvidenceItem], ...]:
    out: dict[str, EvidenceItem] = {}
    for feature in model_top_features:
        if feature in known_names or feature in out:
            continue
        out[feature] = EvidenceItem(
            description=f"{feature}: statistical association weighted by the calibrated model",
            source=f"logistic-regression model {model_version}",
            evidence_category="statistical_association",
        )
    return tuple(out.items())


def assemble_evidence(
    antibiotic: str,
    vector: GenomeFeatureVector,
    *,
    gate_fired: bool,
    model_top_features: tuple[str, ...] = (),
    model_version: str | None = None,
) -> EvidenceBundle:
    """Build the evidence + row-level category for one antibiotic row.

    When the deterministic gate fired, only curated known-mechanism evidence is cited (the gate
    short-circuits the model). Otherwise curated known hits are cited as ``known_mechanism`` and
    the model's weighted features as ``statistical_association``; the row category is the
    strongest cited category, and an empty bundle (``no_signal``) is returned when nothing
    concrete supports the call.
    """
    known = _known_items(antibiotic, vector)
    if gate_fired:
        # Gate fires only on curated mechanism hits, so `known` is non-empty here.
        return EvidenceBundle(
            evidence=tuple(item for _, item in known),
            supporting_features=tuple(name for name, _ in known),
            category="known_mechanism",
        )

    known_names = frozenset(name for name, _ in known)
    statistical = _statistical_items(model_top_features, known_names, model_version or "unknown")
    items = (*known, *statistical)
    if not items:
        return EvidenceBundle(evidence=(), supporting_features=(), category="no_signal")

    category: EvidenceCategory = "statistical_association"
    if known:
        category = "known_mechanism"
    return EvidenceBundle(
        evidence=tuple(item for _, item in items),
        supporting_features=tuple(name for name, _ in items),
        category=category,
    )
