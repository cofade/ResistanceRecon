"""In-process orchestrator: FASTA -> reader -> features -> predictor -> report -> narrative.

The single pipeline both the FastAPI backend (api/) and the Streamlit UI (ui/) call --
ADR-0022 chose an in-process orchestrator over a Streamlit-calls-FastAPI-over-HTTP split so
the UI has no network hop and no second process to keep alive for a one-click demo deploy.
Every module this file composes is frozen (reader/features/predictor/report/llm/kb); this
file owns none of their logic, only the wiring and the adapter between predictor primitives
and the report package's decoupled input contract.
"""

from __future__ import annotations

import io
import os
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Protocol

import numpy as np
import numpy.typing as npt

from genome_firewall.constants import SUPPORTED_ANTIBIOTICS, SUPPORTED_SPECIES
from genome_firewall.features.feature_matrix import build_feature_row
from genome_firewall.kb.evidence_rag import EvidenceRAG
from genome_firewall.llm.client import LLMClient
from genome_firewall.predictor.calibration import predict_resistant_proba
from genome_firewall.predictor.conformal import predict_set
from genome_firewall.predictor.errors import (
    AmrfinderDbVersionMismatchError,
    FeatureSchemaMismatchError,
)
from genome_firewall.predictor.model_registry import DrugModel, PredictorRegistry
from genome_firewall.predictor.predict import predict_genome
from genome_firewall.reader.fasta_parser import FastaParseError, parse_fasta
from genome_firewall.reader.feature_builder import build_feature_vector
from genome_firewall.report import DrugPredictionInput, GenomePredictionInputs, build_report
from genome_firewall.report.pipeline import NarrativeEnvelope, narrate_report
from genome_firewall.schemas import AnnotationResult, GenomeFeatureVector, ModelPrediction

#: repo_root/models -- src-layout: service.py -> genome_firewall -> src -> repo_root.
DEFAULT_MODELS_DIR = Path(__file__).resolve().parents[2] / "models"

#: Bundled, offline-safe demo assets (issue #28) -- a committed realistic FASTA (copied from
#: tests/fixtures/reader/573.10001.fna) reused for every demo genome_id, since MockAnnotator
#: selects its fixture purely by genome_id and never reads the FASTA's own content (the same
#: convention tests/annotation/test_mock.py already relies on) -- so one physical file backs
#: every demo entry below without duplicating ~150KB per id.
DEMO_DATA_DIR = Path(__file__).resolve().parent / "demo_data"
DEMO_FASTA_PATH = DEMO_DATA_DIR / "demo_genome.fna"
DEMO_ANNOTATION_FIXTURE_DIR = DEMO_DATA_DIR / "annotations"
#: genome_id -> human-readable label, for the UI's bundled-demo dropdown (issue #28).
DEMO_GENOMES: dict[str, str] = {
    "573.10001": "Resistance markers present (gate + model-driven verdicts)",
    "573.10002": "Clean genome (no resistance markers detected)",
}

#: How many present features to surface as report.inputs.DrugPredictionInput.model_top_features
#: (mirrors predictor.predict._TOP_K_EVIDENCE so the report's attribution depth matches the
#: sovereign predictor path).
_TOP_K_ADAPTER_FEATURES = 5


class Annotator(Protocol):
    """Structural contract shared by MockAnnotator and RealAnnotator (golden rule #6: the real
    AMRFinderPlus path only ever runs behind this seam, never imported directly by api/ui/).
    """

    def annotate(self, fasta_path: Path, *, genome_id: str) -> AnnotationResult: ...


class RealAnnotator:
    """Adapts the free-function ``annotation.amrfinder.run_amrfinder`` to the ``Annotator``
    protocol so api/ui can depend on one uniform shape regardless of which backend is active.
    Constructing this does not itself touch Docker -- only calling ``.annotate`` does.
    """

    def annotate(self, fasta_path: Path, *, genome_id: str) -> AnnotationResult:
        # Imported lazily so importing genome_firewall.service never requires anything beyond
        # annotation.amrfinder's own (already-lazy) subprocess dependency to be resolvable.
        from genome_firewall.annotation.amrfinder import run_amrfinder

        return run_amrfinder(fasta_path, genome_id=genome_id)


def default_annotator(*, fixture_dir: Path | None = None) -> Annotator:
    """The annotator api/ and ui/ use when the caller does not inject one explicitly.

    Real Docker/WSL2 AMRFinderPlus only when explicitly opted into via ``GF_USE_DOCKER=1``
    (golden rule #6: never on by default, never in CI); otherwise ``MockAnnotator`` over the
    bundled demo fixtures, so the demo always works out of the box, offline, with no Docker.
    """
    if os.environ.get("GF_USE_DOCKER") == "1":
        return RealAnnotator()
    from genome_firewall.annotation.mock import MockAnnotator

    return MockAnnotator(fixture_dir or DEMO_ANNOTATION_FIXTURE_DIR)


def using_docker_annotator(annotator: Annotator) -> bool:
    """True iff ``annotator`` is the real Docker/WSL2 backend -- lets the UI show an honest
    mock-vs-real indicator instead of silently pretending every run used real annotation."""
    return isinstance(annotator, RealAnnotator)


class PipelineError(RuntimeError):
    """A tool/infra failure inside ``analyze_genome``: an ``ok=False`` annotation envelope, or
    a genome whose annotation basis is incompatible with the trained models. The API maps this
    to a 503 ``{ok:false,error}`` envelope; the message is always one of predictor/annotation's
    own already-safe, non-sensitive strings -- never a raw traceback.
    """


@contextmanager
def materialize_upload(data: bytes, *, suffix: str = ".fasta") -> Iterator[Path]:
    """Write uploaded FASTA bytes to a private temp file.

    ``Annotator.annotate`` needs a real ``Path`` (mirroring ``run_amrfinder``'s Docker
    bind-mount contract, which reads the file from disk), so an in-memory upload from the API
    or the Streamlit file_uploader must be materialized before it can flow into the pipeline.
    The temp directory -- and the file in it -- is removed when the context exits.
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        path = Path(tmp_dir) / f"upload{suffix}"
        path.write_bytes(data)
        yield path


def _top_features(row: npt.NDArray[np.float64], drug_model: DrugModel) -> tuple[str, ...]:
    """Present (nonzero) features for one drug, ranked by |signed LR coefficient| -- the same
    ranking predictor.predict._present_contributions uses, recomputed here since that helper
    is private to predict.py and this adapter emits primitives, not the module's own verdict.
    """
    coef_by_feature = {c.feature: c.coefficient for c in drug_model.coefficients}
    present = [
        (name, coef_by_feature.get(name, 0.0))
        for name, value in zip(drug_model.feature_schema.feature_names, row, strict=True)
        if value != 0.0
    ]
    present.sort(key=lambda item: (-abs(item[1]), item[0]))
    return tuple(name for name, _weight in present[:_TOP_K_ADAPTER_FEATURES])


def to_prediction_inputs(
    vector: GenomeFeatureVector, registry: PredictorRegistry
) -> GenomePredictionInputs:
    """Bridge predictor primitives -> report.inputs.DrugPredictionInput, one row per panel drug.

    Deliberately emits no verdict: report.build_report derives it from the conformal set via
    the exact same verdict_for_conformal_set predictor.predict uses internally, so the sovereign
    predict_genome() path (golden rule #1) and the report path can never silently disagree --
    pinned by tests/service/test_verdict_reconciliation.py. This costs a second pass of the
    same ~5 logistic-regression evaluations predict_genome already did (negligible per genome)
    in exchange for the honest ADR-0020 evidence-category tagging build_report performs, which
    predictor.predict's own output does not carry.
    """
    drugs: list[DrugPredictionInput] = []
    for antibiotic in SUPPORTED_ANTIBIOTICS:
        drug_model = registry.get(antibiotic)
        if drug_model is None:
            drugs.append(
                DrugPredictionInput(antibiotic=antibiotic, vector=vector, insufficient_data=True)
            )
            continue
        row, _oov = build_feature_row(vector, drug_model.feature_schema)
        p_resistant = float(
            predict_resistant_proba(drug_model.calibrated_model, row.reshape(1, -1))[0]
        )
        conformal_set = predict_set(drug_model.conformal, p_resistant)
        drugs.append(
            DrugPredictionInput(
                antibiotic=antibiotic,
                vector=vector,
                model_prediction=ModelPrediction(
                    probability_resistant=p_resistant, model_version=drug_model.version
                ),
                conformal_set=conformal_set,
                model_top_features=_top_features(row, drug_model),
            )
        )
    return GenomePredictionInputs(genome_id=vector.genome_id, drugs=tuple(drugs))


def analyze_genome(
    fasta_path: Path,
    *,
    genome_id: str,
    annotator: Annotator,
    registry: PredictorRegistry,
    species: str = SUPPORTED_SPECIES[0],
    client: LLMClient | None = None,
    retriever: EvidenceRAG | None = None,
) -> NarrativeEnvelope:
    """FASTA -> parse -> annotate -> features -> predict -> report -> narrate.

    The one pipeline api/main.py and ui/app.py both call (ADR-0022) so there is exactly one
    FASTA -> NarrativeEnvelope path in this codebase. ``fasta_path`` must already be on disk --
    an in-memory upload is materialized first via ``materialize_upload`` (both Annotator
    implementations read a real file, mirroring run_amrfinder's Docker bind-mount contract).

    Raises ``FastaParseError`` (from reader.fasta_parser) for a structurally invalid upload --
    the caller maps this to a 422 client error. Raises ``PipelineError`` for a tool/infra
    failure: an ``ok=False`` annotation envelope, or a genome whose annotation basis (AMRFinder
    DB version / feature schema_version) disagrees with the trained models -- the caller maps
    this to a 503 ``{ok:false,error}`` envelope. Never raises a bare/unexpected exception past
    these two typed errors for a well-formed call; an annotator/registry misconfiguration at
    call time is the one exception (fails loud, by design -- see api/main.py's lifespan).
    """
    # Validate from an in-memory copy, not the on-disk path: parse_fasta(Path) leaves Biopython's
    # SeqIO handle open when a parse FAILS (frozen reader/), which on Windows blocks the upload's
    # TemporaryDirectory cleanup (WinError 32) and masks the FastaParseError. A StringIO holds no
    # OS handle, so the temp file is free to clean up regardless of parse outcome. parse_fasta
    # explicitly accepts a text stream for exactly this (an uploaded file wrapped in io.StringIO).
    try:
        fasta_text = fasta_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise FastaParseError(f"could not read FASTA content: {exc}") from exc
    parse_fasta(io.StringIO(fasta_text), genome_id=genome_id, species=species)
    annotation = annotator.annotate(fasta_path, genome_id=genome_id)
    if not annotation.ok:
        raise PipelineError(f"annotation failed ({annotation.source}): {annotation.error}")
    if annotation.data is None or annotation.amrfinder_db_version is None:
        raise PipelineError(
            f"annotation reported ok=True but returned no usable data ({annotation.source})"
        )

    vector = build_feature_vector(
        genome_id, annotation.data, amrfinder_db_version=annotation.amrfinder_db_version
    )

    try:
        # The sovereign verdict path (golden rule #1): run for its fail-loud DB-version /
        # schema-version compatibility guard before any report is built. Its own return value
        # is not otherwise consumed here -- build_report (below) re-derives report rows via the
        # decoupled report.inputs contract, honestly per ADR-0020's evidence-category policy;
        # tests/service/test_verdict_reconciliation.py pins the two paths to always agree.
        predict_genome(vector, registry)
    except (AmrfinderDbVersionMismatchError, FeatureSchemaMismatchError) as exc:
        raise PipelineError(str(exc)) from exc

    inputs = to_prediction_inputs(vector, registry)
    report = build_report(inputs)
    return narrate_report(report, client=client, retriever=retriever)
