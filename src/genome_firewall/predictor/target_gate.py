"""Deterministic molecular-target / known-mechanism gate (issue #19).

Authoritative over the model where it fires: a called known resistance mechanism is a fact,
not a statistical estimate, so a genome carrying one short-circuits the LR+conformal step
with ``evidence_category=known_mechanism`` and a fixed high confidence.

**One-directional (ADR-0018, grounded in the challenge brief).** The gate only ever FORCES
``likely_to_fail`` -- it NEVER forces ``likely_to_work``. The brief is explicit: the system
must "account for the presence of the drug's molecular target, so [it] does not report
'likely to work' based solely on the absence of resistance markers." A carbapenemase-absent
genome is therefore NOT gate-forced to 'work' (the porin-loss route means absence != S);
susceptibility is concluded only by the calibrated model + conformal (which can also
no-call). For the five panel drugs the molecular target (PBPs, gyrase/topoisomerase-IV, 30S
rRNA, DHFR/DHPS) is an essential, universally-present gene in K. pneumoniae, so
``target_present`` is True throughout and the target-absence branch is a recorded safety
formalism, never an intrinsic-resistance call the data can't support.

Rule membership comes from features.mechanisms (the single source of truth shared with the
engineered features). Pure and LLM-free.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

from pydantic import BaseModel, ConfigDict

from genome_firewall.features import mechanisms
from genome_firewall.predictor.dataset import canonicalize_antibiotic
from genome_firewall.schemas import GateResult, GenomeFeatureVector


class GateEvaluation(BaseModel):
    """Full outcome of evaluating the gate for one (antibiotic, genome) pair.

    ``result`` is the boundary GateResult predict.py consumes; ``matched_genes`` and
    ``subclass_citations`` feed known-mechanism evidence assembly.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    result: GateResult
    matched_genes: tuple[str, ...] = ()
    subclass_citations: tuple[str, ...] = ()
    #: True for every panel drug (essential target present in K. pneumoniae); None when the
    #: antibiotic is outside the supported panel.
    target_present: bool | None = None


def _subclass_citation(vector: GenomeFeatureVector, gene: str) -> str:
    subclass = vector.gene_drug_subclass.get(gene, "unknown")
    return f"{gene} (AMRFinderPlus Subclass={subclass})"


def _fired(
    vector: GenomeFeatureVector,
    rule: str,
    matched: Sequence[str],
    *,
    with_subclass: bool = False,
) -> GateEvaluation:
    citations = tuple(_subclass_citation(vector, gene) for gene in matched) if with_subclass else ()
    return GateEvaluation(
        # forced_verdict is ALWAYS likely_to_fail -- the one-directional invariant.
        result=GateResult(fired=True, rule=rule, forced_verdict="likely_to_fail"),
        matched_genes=tuple(matched),
        subclass_citations=citations,
        target_present=True,
    )


def _not_fired() -> GateEvaluation:
    return GateEvaluation(result=GateResult(fired=False), target_present=True)


def _meropenem(vector: GenomeFeatureVector) -> GateEvaluation:
    carbapenemases = mechanisms.carbapenemase_hits(vector)
    if carbapenemases:
        return _fired(vector, "carbapenemase_present", carbapenemases, with_subclass=True)
    # Carbapenemase-absent does NOT fire: the porin-loss route means absence != susceptible.
    return _not_fired()


def _ceftriaxone(vector: GenomeFeatureVector) -> GateEvaluation:
    hits = mechanisms.cephalosporin_resistance_hits(vector)
    if hits:
        return _fired(vector, "esbl_ampc_or_carbapenemase_present", hits, with_subclass=True)
    return _not_fired()


def _ciprofloxacin(vector: GenomeFeatureVector) -> GateEvaluation:
    qrdr = mechanisms.qrdr_mutations(vector)
    pmqr = mechanisms.pmqr_hits(vector)
    # A single QRDR mutation or single PMQR gene is often only reduced susceptibility; only
    # combinations reliably give high-level resistance (antibiotic-panel.md).
    if len(qrdr) >= 2:
        return _fired(vector, "qrdr_double_mutation", qrdr)
    if len(qrdr) >= 1 and pmqr:
        return _fired(vector, "qrdr_plus_pmqr", (*qrdr, *pmqr))
    return _not_fired()


def _gentamicin(vector: GenomeFeatureVector) -> GateEvaluation:
    rmtases = mechanisms.rmtase_hits(vector)
    if rmtases:
        return _fired(vector, "16s_rmtase_present", rmtases, with_subclass=True)
    # AME-only genotypes are drug-specific/moderate -> left to the model, not hard-fired.
    return _not_fired()


def _trimethoprim_sulfamethoxazole(vector: GenomeFeatureVector) -> GateEvaluation:
    hits = (*mechanisms.sul_hits(vector), *mechanisms.dfr_hits(vector))
    if hits:
        return _fired(vector, "sul_or_dfr_present", hits)
    return _not_fired()


_GATE_HANDLERS: dict[str, Callable[[GenomeFeatureVector], GateEvaluation]] = {
    "meropenem": _meropenem,
    "ceftriaxone": _ceftriaxone,
    "ciprofloxacin": _ciprofloxacin,
    "gentamicin": _gentamicin,
    "trimethoprim-sulfamethoxazole": _trimethoprim_sulfamethoxazole,
}


def evaluate_gate(antibiotic: str, vector: GenomeFeatureVector) -> GateEvaluation:
    """Evaluate the deterministic gate for one antibiotic against one genome.

    Returns a not-fired evaluation with ``target_present=None`` for an antibiotic outside the
    supported panel. The gate is one-directional: a fired result always forces
    ``likely_to_fail`` and never ``likely_to_work``.
    """
    handler = _GATE_HANDLERS.get(canonicalize_antibiotic(antibiotic))
    if handler is None:
        return GateEvaluation(result=GateResult(fired=False), target_present=None)
    return handler(vector)
