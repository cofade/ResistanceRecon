"""Unit coverage for the service orchestrator + adapter (issue #7): the DrugPredictionInput
adapter shapes, the annotator resolution, temp-file materialization, and the two typed error
paths (FastaParseError for a bad upload, PipelineError for a tool/infra failure). Offline.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

import genome_firewall.annotation.amrfinder as amrfinder
from genome_firewall import service
from genome_firewall.annotation.mock import MockAnnotator
from genome_firewall.constants import SUPPORTED_ANTIBIOTICS
from genome_firewall.reader.fasta_parser import FastaParseError
from genome_firewall.schemas import AnnotationResult
from tests._demo import demo_vector, load_demo_registry


def test_adapter_emits_one_input_per_panel_drug_with_primitives() -> None:
    inputs = service.to_prediction_inputs(demo_vector("573.10001"), load_demo_registry())

    assert tuple(d.antibiotic for d in inputs.drugs) == SUPPORTED_ANTIBIOTICS
    for drug in inputs.drugs:
        # Every panel drug is trained in the committed registry -> primitives present, no verdict.
        assert drug.model_prediction is not None
        assert 0.0 <= drug.model_prediction.probability_resistant <= 1.0
        assert drug.conformal_set is not None
        assert not drug.insufficient_data


def test_adapter_marks_untrained_drug_insufficient() -> None:
    registry = load_demo_registry()
    without_gentamicin = dataclasses.replace(
        registry, drugs={k: v for k, v in registry.drugs.items() if k != "gentamicin"}
    )

    inputs = service.to_prediction_inputs(demo_vector("573.10001"), without_gentamicin)

    gentamicin = next(d for d in inputs.drugs if d.antibiotic == "gentamicin")
    assert gentamicin.insufficient_data
    assert gentamicin.model_prediction is None
    assert gentamicin.conformal_set is None


def test_bad_annotation_envelope_raises_pipeline_error() -> None:
    with pytest.raises(service.PipelineError, match="annotation failed"):
        service.analyze_genome(
            service.DEMO_FASTA_PATH,
            genome_id="no-such-genome",
            annotator=service.default_annotator(),
            registry=load_demo_registry(),
        )


def test_invalid_fasta_raises_fasta_parse_error(tmp_path: Path) -> None:
    bad = tmp_path / "bad.fasta"
    bad.write_text("this is not a FASTA file", encoding="utf-8")
    with pytest.raises(FastaParseError):
        service.analyze_genome(
            bad,
            genome_id="573.10001",
            annotator=service.default_annotator(),
            registry=load_demo_registry(),
        )


def test_db_version_mismatch_raises_pipeline_error() -> None:
    class _WrongDbAnnotator:
        def annotate(self, fasta_path: Path, *, genome_id: str) -> AnnotationResult:
            real = MockAnnotator(service.DEMO_ANNOTATION_FIXTURE_DIR).annotate(
                fasta_path, genome_id=genome_id
            )
            return real.model_copy(update={"amrfinder_db_version": "9999-01-01.1"})

    with pytest.raises(service.PipelineError, match="DB version"):
        service.analyze_genome(
            service.DEMO_FASTA_PATH,
            genome_id="573.10001",
            annotator=_WrongDbAnnotator(),
            registry=load_demo_registry(),
        )


def test_materialize_upload_writes_then_cleans_up() -> None:
    with service.materialize_upload(b">c1\nACGT\n") as path:
        assert path.exists()
        assert path.read_bytes() == b">c1\nACGT\n"
    assert not path.exists()  # the temp dir is removed on context exit


def test_default_annotator_is_mock_without_docker_opt_in(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GF_USE_DOCKER", raising=False)
    annotator = service.default_annotator()
    assert not service.using_docker_annotator(annotator)


def test_default_annotator_is_real_when_opted_in(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GF_USE_DOCKER", "1")
    annotator = service.default_annotator()
    assert service.using_docker_annotator(annotator)


def test_real_annotator_forwards_to_run_amrfinder(monkeypatch: pytest.MonkeyPatch) -> None:
    sentinel = AnnotationResult(ok=False, source="docker:test", error="stub (no docker call)")
    monkeypatch.setattr(amrfinder, "run_amrfinder", lambda path, *, genome_id: sentinel)
    result = service.RealAnnotator().annotate(service.DEMO_FASTA_PATH, genome_id="573.10001")
    assert result is sentinel
