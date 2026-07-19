"""Deterministic AMR-mechanism membership predicates over a GenomeFeatureVector.

Single source of truth for "which genes/mutations mean which resistance mechanism",
transcribed from Documentation/research-findings/antibiotic-panel.md ("Known-mechanism
evidence gene groups"). Shared by features/vocabulary.py (engineered combination features)
and predictor/target_gate.py (the deterministic gate) so both read a genome identically.
Pure and LLM-free (features/ is trust-critical -- scripts/check_import_boundary.py forbids
importing genome_firewall.llm here).

Beta-lactam tiers use AMRFinderPlus's own resistance-hierarchy Subclass
(GenomeFeatureVector.gene_drug_subclass), the authoritative curated classification: a
narrow-spectrum blaSHV-1/blaSHV-11 (Subclass=BETA-LACTAM) never counts as an ESBL, while a
carbapenemase (Subclass=CARBAPENEM) is recognised as hydrolysing cephalosporins too. The
aminoglycoside RMTase-vs-AME split and the quinolone/sulfonamide/trimethoprim families are
matched by gene-symbol family, since Subclass alone does not separate them.
"""

from __future__ import annotations

from collections.abc import Callable, Collection

from genome_firewall.schemas import GenomeFeatureVector

CARBAPENEM_SUBCLASS = "CARBAPENEM"
CEPHALOSPORIN_SUBCLASS = "CEPHALOSPORIN"


def _genes_with_subclass(
    vector: GenomeFeatureVector, subclasses: Collection[str]
) -> tuple[str, ...]:
    return tuple(
        sorted(
            gene
            for gene in vector.gene_presence
            if vector.gene_drug_subclass.get(gene) in subclasses
        )
    )


def _matching_genes(
    vector: GenomeFeatureVector, predicate: Callable[[str], bool]
) -> tuple[str, ...]:
    return tuple(sorted(gene for gene in vector.gene_presence if predicate(gene)))


def carbapenemase_hits(vector: GenomeFeatureVector) -> tuple[str, ...]:
    """Carbapenemases (Subclass=CARBAPENEM): KPC/NDM/OXA-48-like/VIM/IMP -- near-100%
    specificity for meropenem resistance when present (antibiotic-panel.md)."""
    return _genes_with_subclass(vector, {CARBAPENEM_SUBCLASS})


def esbl_ampc_hits(vector: GenomeFeatureVector) -> tuple[str, ...]:
    """ESBL/AmpC genes (Subclass=CEPHALOSPORIN): blaCTX-M, ESBL blaSHV/blaTEM variants,
    blaCMY/DHA AmpC. Excludes narrow blaSHV-1/blaSHV-11 (Subclass=BETA-LACTAM)."""
    return _genes_with_subclass(vector, {CEPHALOSPORIN_SUBCLASS})


def cephalosporin_resistance_hits(vector: GenomeFeatureVector) -> tuple[str, ...]:
    """Every gene that hydrolyses 3rd-gen cephalosporins: ESBL/AmpC PLUS carbapenemases
    (which also hydrolyse cephalosporins), so a KPC producer is correctly called
    ceftriaxone-resistant rather than left to the model."""
    return _genes_with_subclass(vector, {CEPHALOSPORIN_SUBCLASS, CARBAPENEM_SUBCLASS})


def _is_rmtase(symbol: str) -> bool:
    lowered = symbol.lower()
    return lowered == "arma" or lowered.startswith("rmt")


def rmtase_hits(vector: GenomeFeatureVector) -> tuple[str, ...]:
    """16S rRNA methyltransferases (armA, rmtB/C/D...) -- near-universal high-level
    pan-aminoglycoside resistance; the strongest single gentamicin predictor."""
    return _matching_genes(vector, _is_rmtase)


def _is_ame(symbol: str) -> bool:
    return symbol.lower().startswith(("aac(", "aph(", "ant("))


def ame_hits(vector: GenomeFeatureVector) -> tuple[str, ...]:
    """Aminoglycoside-modifying enzymes (aac/aph/ant) -- secondary, drug-specific,
    moderate signal. Never hard-fires the gentamicin gate; a model feature only."""
    return _matching_genes(vector, _is_ame)


def _is_pmqr(symbol: str) -> bool:
    lowered = symbol.lower()
    return lowered.startswith(("qnr", "qepa", "oqx")) or "aac(6')-ib-cr" in lowered


def pmqr_hits(vector: GenomeFeatureVector) -> tuple[str, ...]:
    """Plasmid-mediated quinolone resistance: qnrA/B/S, aac(6')-Ib-cr, oqxAB, qepA."""
    return _matching_genes(vector, _is_pmqr)


def _is_sul(symbol: str) -> bool:
    return symbol.lower().startswith("sul")


def sul_hits(vector: GenomeFeatureVector) -> tuple[str, ...]:
    """Sulfonamide dihydropteroate-synthase bypass genes (sul1/sul2/sul3)."""
    return _matching_genes(vector, _is_sul)


def _is_dfr(symbol: str) -> bool:
    return symbol.lower().startswith("dfr")


def dfr_hits(vector: GenomeFeatureVector) -> tuple[str, ...]:
    """Trimethoprim dihydrofolate-reductase bypass genes (dfrA family)."""
    return _matching_genes(vector, _is_dfr)


def _is_qrdr(mutation: str) -> bool:
    lowered = mutation.lower()
    return any(lowered.startswith(prefix) for prefix in ("gyra_", "gyra-", "parc_", "parc-"))


def qrdr_mutations(vector: GenomeFeatureVector) -> tuple[str, ...]:
    """Quinolone resistance-determining-region point mutations in gyrA / parC."""
    return tuple(sorted(mutation for mutation in vector.point_mutations if _is_qrdr(mutation)))


def porin_disruptions(vector: GenomeFeatureVector) -> tuple[str, ...]:
    """Disrupting mutations in the ompK35/ompK36 porins (the carbapenemase-negative
    carbapenem-resistance route) -- POINT_DISRUPT hits recorded by feature_builder."""
    return tuple(
        sorted(name for name in vector.point_mutation_disrupt if name.lower().startswith("ompk"))
    )
