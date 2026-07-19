"""FastAPI backend (issue #27): POST /predict, GET /health, /antibiotics, /model-card.

A thin HTTP wrapper around service.analyze_genome -- the same in-process orchestrator the
Streamlit UI calls directly (ADR-0022: this app is a separate deliverable surface, not the
UI's only way to reach the pipeline). Every tool/pipeline failure returns a structured
``{ok:false, error}`` envelope at 503; a malformed request returns 422. Never a traceback
(see api/errors.py).
"""

from __future__ import annotations

import json
import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any

from fastapi import Depends, FastAPI, File, Form, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict

from genome_firewall import __version__
from genome_firewall.api.errors import (
    handle_client_error,
    handle_pipeline_error,
    handle_unexpected_error,
)
from genome_firewall.constants import LAB_CONFIRMATION_DISCLAIMER, SUPPORTED_ANTIBIOTICS
from genome_firewall.kb.embedder import HashingBagOfWordsEmbedder
from genome_firewall.kb.evidence_rag import EvidenceRAG
from genome_firewall.llm.client import LLMClient
from genome_firewall.llm.factory import make_client
from genome_firewall.predictor.model_registry import STATUS_TRAINED, PredictorRegistry, drug_slug
from genome_firewall.reader.fasta_parser import FastaParseError
from genome_firewall.report.pipeline import NarrativeEnvelope
from genome_firewall.service import (
    DEFAULT_MODELS_DIR,
    Annotator,
    PipelineError,
    analyze_genome,
    default_annotator,
    materialize_upload,
)

#: Same safe charset as annotation.amrfinder's own (private) genome_id guard -- genome_id never
#: touches a filesystem path here (materialize_upload always writes a fixed "upload.fasta"
#: filename), but rejecting anything odd up front keeps every downstream error message
#: (MockAnnotator's fixture lookup, Docker's --name) predictable and traceback-free.
_SAFE_GENOME_ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,128}$")


@dataclass
class AppState:
    """Everything loaded once at startup and reused across requests (issue #27's lifespan)."""

    registry: PredictorRegistry
    annotator: Annotator
    client: LLMClient | None
    retriever: EvidenceRAG
    results_summary: dict[str, Any]
    per_drug_cards: dict[str, str]


def _load_per_drug_cards(models_dir: Path, registry: PredictorRegistry) -> dict[str, str]:
    cards: dict[str, str] = {}
    for antibiotic in SUPPORTED_ANTIBIOTICS:
        if registry.status(antibiotic) != STATUS_TRAINED:
            continue
        version = registry.entries[antibiotic].latest_version
        if version is None:
            continue
        card_path = models_dir / drug_slug(antibiotic) / version / "model_card.md"
        if card_path.exists():
            cards[antibiotic] = card_path.read_text(encoding="utf-8")
    return cards


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Load the registry, annotator, LLM client, and evidence retriever once (issue #27).

    Deliberately fails loud: if the registry cannot be loaded, the app does not start rather
    than serve a demo that would 503 on every request -- the same "never serve broken state"
    posture the rest of this codebase already takes (predictor/errors.py, annotation/*.py).
    """
    registry = PredictorRegistry.load(DEFAULT_MODELS_DIR)
    results_summary = json.loads(
        (DEFAULT_MODELS_DIR / "results_summary.json").read_text(encoding="utf-8")
    )
    app.state.gf = AppState(
        registry=registry,
        annotator=default_annotator(),
        client=make_client(),
        retriever=EvidenceRAG.from_seed(embedder=HashingBagOfWordsEmbedder()),
        results_summary=results_summary,
        per_drug_cards=_load_per_drug_cards(DEFAULT_MODELS_DIR, registry),
    )
    yield


def get_app_state(request: Request) -> AppState:
    state: AppState = request.app.state.gf
    return state


class PredictSuccess(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ok: bool = True
    envelope: NarrativeEnvelope


class HealthResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str = "ok"
    version: str
    models_loaded: tuple[str, ...]


class AntibioticStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    antibiotic: str
    status: str | None


class AntibioticsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    antibiotics: tuple[AntibioticStatus, ...]
    disclaimer: str = LAB_CONFIRMATION_DISCLAIMER


class ModelCardResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    results_summary: dict[str, Any]
    per_drug_cards: dict[str, str]
    disclaimer: str = LAB_CONFIRMATION_DISCLAIMER


def create_app() -> FastAPI:
    """App factory (issue #27) -- lets tests build isolated app instances if ever needed,
    while the module-level ``app`` below is what ``uvicorn genome_firewall.api.main:app``
    serves.
    """
    app = FastAPI(
        title="Genome Firewall API",
        version=__version__,
        lifespan=lifespan,
    )
    # Demo-permissive CORS: this is a hackathon/demo deployment behind no auth of its own;
    # tighten allow_origins before any real production deploy.
    app.add_middleware(
        CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
    )
    app.add_exception_handler(FastaParseError, handle_client_error)
    app.add_exception_handler(PipelineError, handle_pipeline_error)
    app.add_exception_handler(Exception, handle_unexpected_error)

    @app.get("/health", response_model=HealthResponse)
    async def health(state: Annotated[AppState, Depends(get_app_state)]) -> HealthResponse:
        return HealthResponse(
            version=__version__, models_loaded=tuple(sorted(state.registry.drugs))
        )

    @app.get("/antibiotics", response_model=AntibioticsResponse)
    async def antibiotics(
        state: Annotated[AppState, Depends(get_app_state)],
    ) -> AntibioticsResponse:
        return AntibioticsResponse(
            antibiotics=tuple(
                AntibioticStatus(antibiotic=a, status=state.registry.status(a))
                for a in SUPPORTED_ANTIBIOTICS
            )
        )

    @app.get("/model-card", response_model=ModelCardResponse)
    async def model_card(
        state: Annotated[AppState, Depends(get_app_state)],
    ) -> ModelCardResponse:
        return ModelCardResponse(
            results_summary=state.results_summary, per_drug_cards=state.per_drug_cards
        )

    @app.post("/predict", response_model=PredictSuccess)
    async def predict(
        state: Annotated[AppState, Depends(get_app_state)],
        fasta_file: Annotated[UploadFile, File(description="Genome assembly FASTA upload")],
        genome_id: Annotated[str, Form(description="Genome identifier")],
        narrate: Annotated[
            bool, Form(description="Attempt the LLM narrative if configured")
        ] = True,
    ) -> PredictSuccess:
        if not _SAFE_GENOME_ID_RE.match(genome_id):
            raise FastaParseError(
                f"invalid genome_id {genome_id!r}: must match {_SAFE_GENOME_ID_RE.pattern}"
            )
        data = await fasta_file.read()
        with materialize_upload(data) as fasta_path:
            envelope = analyze_genome(
                fasta_path,
                genome_id=genome_id,
                annotator=state.annotator,
                registry=state.registry,
                client=state.client if narrate else None,
                retriever=state.retriever,
            )
        return PredictSuccess(envelope=envelope)

    return app


app = create_app()
