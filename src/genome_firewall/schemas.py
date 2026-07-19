"""Single source of truth Pydantic contracts for every value crossing a module boundary
(golden rule #5 -- no raw dicts cross a boundary). extra='forbid' and closed Literal
enums everywhere; cross-field validators enforce the safety invariants in
Documentation/08-crosscutting-concepts/README.md (the no-call contract and the
Ground-Truth-First evidence rule) at the type layer, not just by convention.

Every module downstream (reader/, annotation/, features/, predictor/, report/) imports
from here. Must not import genome_firewall.llm (golden rule #1; enforced by
scripts/check_import_boundary.py).
"""

from __future__ import annotations

from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from genome_firewall.constants import LAB_CONFIRMATION_DISCLAIMER


class _StrictModel(BaseModel):
    """Shared config: no undeclared fields, immutable once constructed."""

    model_config = ConfigDict(extra="forbid", frozen=True)


# ---------------------------------------------------------------------------
# Module 01 -- Genome Reader (reader/, annotation/)
# ---------------------------------------------------------------------------


class ContigRecord(_StrictModel):
    """One contig from an assembled genome FASTA."""

    contig_id: str
    length: int = Field(gt=0)
    description: str = ""


class GenomeInput(_StrictModel):
    """A parsed, validated genome ready for annotation."""

    genome_id: str
    species: str
    contigs: tuple[ContigRecord, ...] = Field(min_length=1)


ElementType = Literal["AMR", "STRESS", "VIRULENCE"]
ElementSubtype = Literal[
    "AMR",
    "POINT",
    "POINT_DISRUPT",
    "ACID",
    "BIOCIDE",
    "HEAT",
    "METAL",
    "VIRULENCE",
    "ANTIGEN",
    "STX_TYPE",
]
#: Real AMRFinderPlus output, confirmed against a live Docker run (ncbi/amr:4.2.7-2026-05-15.1)
#: against a real K. pneumoniae genome -- NOT the bare ALLELE/EXACT/BLAST/PARTIAL/POINT names
#: the pre-implementation research doc summarized. Every BLAST-based method carries an X/P/N
#: suffix for how the hit was found (X=translated nucleotide, P=protein, N=nucleotide BLAST,
#: point mutations only); since annotation/ always runs `-n` nucleotide-only per ADR-0002, the
#: *P-suffixed variants never fire in practice, but are kept in the closed set for fidelity to
#: what AMRFinderPlus itself defines (see the ncbi/amr wiki's Interpreting-results page).
AmrMethod = Literal[
    "ALLELEX",
    "ALLELEP",
    "EXACTX",
    "EXACTP",
    "BLASTX",
    "BLASTP",
    "PARTIALX",
    "PARTIALP",
    "PARTIAL_CONTIG_ENDX",
    "PARTIAL_CONTIG_ENDP",
    "INTERNAL_STOP",
    "HMM",
    "POINTX",
    "POINTP",
    "POINTN",
]
AmrScope = Literal["core", "plus"]
Strand = Literal["+", "-"]


class AmrFeature(_StrictModel):
    """One AMRFinderPlus hit row. Column semantics: research-findings/amrfinderplus-features.md."""

    gene_symbol: str
    sequence_name: str
    scope: AmrScope
    element_type: ElementType
    element_subtype: ElementSubtype
    drug_class: str | None = None
    drug_subclass: str | None = None
    method: AmrMethod
    pct_coverage: float = Field(ge=0.0, le=100.0)
    pct_identity: float = Field(ge=0.0, le=100.0)
    contig_id: str
    start: int = Field(ge=1)
    stop: int = Field(ge=1)
    strand: Strand
    #: Traceable-evidence citation (golden rule #3) -- populated for essentially every hit;
    #: Protein id/HMM accession/HMM description are omitted since they are always "NA" under
    #: annotation/'s fixed `-n` nucleotide-only invocation (confirmed against a live run).
    closest_reference_accession: str | None = None
    closest_reference_name: str | None = None


class AnnotationResult(_StrictModel):
    """The {ok, source, error} envelope every annotation/ call returns (golden rule #6)."""

    ok: bool
    source: str
    error: str | None = None
    data: tuple[AmrFeature, ...] | None = None
    amrfinder_db_version: str | None = None

    @model_validator(mode="after")
    def _envelope_is_consistent(self) -> Self:
        if self.ok:
            if self.data is None:
                raise ValueError("ok=True requires data")
            if self.error is not None:
                raise ValueError("ok=True must not carry an error")
        else:
            if self.error is None:
                raise ValueError("ok=False requires error")
            if self.data is not None:
                raise ValueError("ok=False must not carry data")
        return self


class GenomeFeatureVector(_StrictModel):
    """Versioned, ML-ready feature vector built from AmrFeature calls (reader/feature_builder.py).

    Two tables per the research findings: gene presence/absence and point mutations, each
    kept separate since they are mechanistically different (acquired gene vs. chromosomal
    target mutation). `gene_presence_method` keeps Method as an auxiliary QC column per gene
    rather than collapsing it away, and PARTIAL_CONTIG_END genes are flagged separately from
    a hard PARTIAL cutoff since they are frequently assembly-fragmentation artifacts.
    """

    genome_id: str
    schema_version: str
    amrfinder_db_version: str
    gene_presence: dict[str, bool] = Field(default_factory=dict)
    gene_presence_method: dict[str, AmrMethod] = Field(default_factory=dict)
    #: >1 means multiple AMRFinderPlus rows matched this gene (different loci/contigs) --
    #: kept explicit rather than silently collapsed, per the research findings' guidance
    #: on near-duplicate/multi-contig hits for the same gene.
    gene_hit_count: dict[str, int] = Field(default_factory=dict)
    #: Resolved Class/Subclass per presence gene (from the TSV directly, or from
    #: ReferenceGeneCatalog.txt when the TSV left it blank -- ADR-0013). A gene present
    #: in `gene_presence` but absent here is exactly `unmapped_class_genes`.
    gene_drug_class: dict[str, str] = Field(default_factory=dict)
    gene_drug_subclass: dict[str, str] = Field(default_factory=dict)
    point_mutations: dict[str, bool] = Field(default_factory=dict)
    point_mutation_disrupt: dict[str, bool] = Field(default_factory=dict)
    partial_contig_end_genes: tuple[str, ...] = ()
    unmapped_class_genes: tuple[str, ...] = ()


# ---------------------------------------------------------------------------
# Module 02 -- Predictor (deterministic gate + calibrated model + conformal).
# The SOLE source of every verdict/confidence (golden rule #1).
# ---------------------------------------------------------------------------

EvidenceCategory = Literal["known_mechanism", "statistical_association", "no_signal"]
Verdict = Literal["likely_to_work", "likely_to_fail", "no_call"]
SirLabel = Literal["S", "R"]


class GateResult(_StrictModel):
    """Deterministic molecular-target-gate outcome for one (genome, antibiotic) pair."""

    fired: bool
    rule: str | None = None
    forced_verdict: Verdict | None = None

    @model_validator(mode="after")
    def _fired_is_consistent(self) -> Self:
        if self.fired and (self.rule is None or self.forced_verdict is None):
            raise ValueError("fired=True requires rule and forced_verdict")
        if not self.fired and (self.rule is not None or self.forced_verdict is not None):
            raise ValueError("fired=False must not carry rule/forced_verdict")
        return self


class ModelPrediction(_StrictModel):
    """Calibrated per-antibiotic logistic-regression output, pre-conformal."""

    probability_resistant: float = Field(ge=0.0, le=1.0)
    model_version: str


class ConformalSet(_StrictModel):
    """Split-conformal prediction set at the configured alpha (ADR-0004)."""

    labels: tuple[SirLabel, ...]
    alpha: float = Field(gt=0.0, lt=1.0)

    @model_validator(mode="after")
    def _labels_do_not_repeat(self) -> Self:
        if len(set(self.labels)) != len(self.labels):
            raise ValueError("labels must not repeat")
        return self


def verdict_for_conformal_set(labels: tuple[SirLabel, ...]) -> Verdict:
    """The no-call contract (gf-architecture-contract): {S}->work, {R}->fail, else no_call."""
    label_set = set(labels)
    if label_set == {"S"}:
        return "likely_to_work"
    if label_set == {"R"}:
        return "likely_to_fail"
    return "no_call"


# ---------------------------------------------------------------------------
# Module 03a -- Decision Report
# ---------------------------------------------------------------------------


class EvidenceItem(_StrictModel):
    """One citable piece of evidence backing a verdict (gene hit, LR coefficient, gate rule)."""

    description: str
    source: str
    evidence_category: EvidenceCategory


class AntibioticPrediction(_StrictModel):
    """The per-antibiotic verdict row on the firewall table."""

    antibiotic: str
    verdict: Verdict
    calibrated_confidence: float = Field(ge=0.0, le=1.0)
    evidence_category: EvidenceCategory
    supporting_features: tuple[str, ...] = ()
    evidence: tuple[EvidenceItem, ...] = ()
    target_present: bool | None = None
    conformal_set: ConformalSet | None = None

    @model_validator(mode="after")
    def _verdict_matches_conformal_set(self) -> Self:
        if self.conformal_set is not None:
            expected = verdict_for_conformal_set(self.conformal_set.labels)
            if expected != self.verdict:
                raise ValueError(
                    f"verdict {self.verdict!r} inconsistent with conformal_set "
                    f"{self.conformal_set.labels!r} (expected {expected!r})"
                )
        return self

    @model_validator(mode="after")
    def _evidence_category_requires_support(self) -> Self:
        if self.evidence_category != "no_signal" and not self.supporting_features:
            raise ValueError(
                f"evidence_category={self.evidence_category!r} requires non-empty "
                "supporting_features (Ground-Truth-First: no claim without evidence)"
            )
        return self

    @model_validator(mode="after")
    def _evidence_category_is_backed_by_a_cited_item(self) -> Self:
        if self.evidence and self.evidence_category not in {
            item.evidence_category for item in self.evidence
        }:
            raise ValueError(
                f"evidence_category={self.evidence_category!r} is not backed by any cited "
                "EvidenceItem of that category (Ground-Truth-First: never claim a category "
                "stronger than what is actually cited)"
            )
        return self


class GenomeReport(_StrictModel):
    """The complete per-genome decision-support report -- the API/UI response contract.

    `disclaimer` is validated against the exact constant, not just defaulted to it --
    one of the three enforcement points for golden rule #4 (the other two are the
    LLM-reviewer check and the non-dismissible UI banner).
    """

    genome_id: str
    predictions: tuple[AntibioticPrediction, ...]
    disclaimer: str = LAB_CONFIRMATION_DISCLAIMER
    narrative_summary: str | None = None

    @model_validator(mode="after")
    def _disclaimer_is_exact(self) -> Self:
        if self.disclaimer != LAB_CONFIRMATION_DISCLAIMER:
            raise ValueError(
                "disclaimer must equal constants.LAB_CONFIRMATION_DISCLAIMER (golden rule #4)"
            )
        return self
