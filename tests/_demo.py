"""Shared EPIC 6 test helpers (not a test module): load the committed registry + build the
demo genome's vector/report once, so the api/ui/service suites need not each re-load joblib
models. Offline: MockAnnotator over the bundled demo fixtures, no Docker, no network.
"""

from __future__ import annotations

from functools import lru_cache

from genome_firewall import service
from genome_firewall.predictor.model_registry import PredictorRegistry
from genome_firewall.reader.feature_builder import build_feature_vector
from genome_firewall.report import build_report
from genome_firewall.report.nl_schemas import NLDrugNarrative, NLReportSection, ReportVerdict
from genome_firewall.schemas import GenomeFeatureVector, GenomeReport


@lru_cache(maxsize=1)
def load_demo_registry() -> PredictorRegistry:
    return PredictorRegistry.load(service.DEFAULT_MODELS_DIR)


@lru_cache(maxsize=4)
def demo_vector(genome_id: str = "573.10001") -> GenomeFeatureVector:
    """The GenomeFeatureVector for a bundled demo genome via the offline MockAnnotator."""
    annotation = service.default_annotator().annotate(service.DEMO_FASTA_PATH, genome_id=genome_id)
    assert annotation.ok and annotation.data is not None
    assert annotation.amrfinder_db_version is not None
    return build_feature_vector(
        genome_id, annotation.data, amrfinder_db_version=annotation.amrfinder_db_version
    )


def demo_report(genome_id: str = "573.10001") -> GenomeReport:
    """The deterministic GenomeReport for a bundled demo genome (same path analyze_genome takes)."""
    return build_report(service.to_prediction_inputs(demo_vector(genome_id), load_demo_registry()))


def passing_section(report: GenomeReport) -> NLReportSection:
    """A narrative guaranteed to pass reviewer.deterministic_precheck for ANY report: the free-text
    summary/caveats carry no verdict/causal phrase, and each per-antibiotic narrative names no
    other drug, asserts no verdict word, uses no causal language, and cites no number.
    """
    return NLReportSection(
        summary="Automated grounding overview of the final decision report.",
        per_antibiotic=tuple(
            NLDrugNarrative(
                antibiotic=p.antibiotic,
                narrative=(
                    "The decision report includes an assessment for this agent; "
                    "refer to the structured verdict for the outcome."
                ),
                citations=(),
            )
            for p in report.predictions
        ),
        caveats=(),
    )


def passing_review() -> ReportVerdict:
    """A reviewer verdict that accepts a narrative (the LLM-judge leg of the accepted path)."""
    return ReportVerdict(grounding_score=1.0, per_claim=(), overall_pass=True)


def failing_review() -> ReportVerdict:
    """A reviewer verdict that REJECTS a narrative -> the pipeline fails closed to the template."""
    return ReportVerdict(grounding_score=0.0, per_claim=(), overall_pass=False)
