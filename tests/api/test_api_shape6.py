"""Integration-test shape #6 (issue #27): request -> structured response, and a tool/pipeline
failure -> a 503 {ok:false,error} envelope that never leaks a traceback. Driven by FastAPI's
TestClient over ASGI (in-memory, no socket), the default offline MockAnnotator, and no LLM key
(-> the deterministic template path). No Docker, no network.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from genome_firewall import service
from genome_firewall.api.main import create_app
from genome_firewall.constants import LAB_CONFIRMATION_DISCLAIMER, SUPPORTED_ANTIBIOTICS

_TRACEBACK_MARKERS = ("Traceback (most recent call last)", 'File "', "\n  line ")


@pytest.fixture(scope="module")
def client() -> Iterator[TestClient]:
    # The context manager runs the app's lifespan (loads registry/annotator/retriever once).
    with TestClient(create_app()) as test_client:
        yield test_client


def _fasta_bytes() -> bytes:
    return service.DEMO_FASTA_PATH.read_bytes()


@pytest.mark.integration
def test_health_lists_loaded_models(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert set(body["models_loaded"]) == set(SUPPORTED_ANTIBIOTICS)


@pytest.mark.integration
def test_antibiotics_carries_panel_and_disclaimer(client: TestClient) -> None:
    body = client.get("/antibiotics").json()
    assert tuple(a["antibiotic"] for a in body["antibiotics"]) == SUPPORTED_ANTIBIOTICS
    assert body["disclaimer"] == LAB_CONFIRMATION_DISCLAIMER


@pytest.mark.integration
def test_model_card_returns_real_committed_numbers(client: TestClient) -> None:
    body = client.get("/model-card").json()
    assert "gentamicin" in body["results_summary"]["drugs"]
    assert body["per_drug_cards"]  # committed per-drug model cards are served
    assert body["disclaimer"] == LAB_CONFIRMATION_DISCLAIMER


@pytest.mark.integration
def test_predict_returns_envelope_with_disclaimer(client: TestClient) -> None:
    response = client.post(
        "/predict",
        files={"fasta_file": ("573.10001.fna", _fasta_bytes(), "text/plain")},
        data={"genome_id": "573.10001"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    envelope = body["envelope"]
    predictions = envelope["report"]["predictions"]
    assert tuple(p["antibiotic"] for p in predictions) == SUPPORTED_ANTIBIOTICS
    assert LAB_CONFIRMATION_DISCLAIMER in envelope["report"]["narrative_summary"]


@pytest.mark.integration
def test_predict_invalid_genome_id_is_422(client: TestClient) -> None:
    response = client.post(
        "/predict",
        files={"fasta_file": ("g.fna", _fasta_bytes(), "text/plain")},
        data={"genome_id": "../evil"},
    )
    assert response.status_code == 422
    body = response.json()
    assert body["ok"] is False
    assert "genome_id" in body["error"]


@pytest.mark.integration
def test_predict_unknown_genome_is_503_without_traceback(client: TestClient) -> None:
    response = client.post(
        "/predict",
        files={"fasta_file": ("573.99999.fna", _fasta_bytes(), "text/plain")},
        data={"genome_id": "573.99999"},
    )
    assert response.status_code == 503
    body = response.json()
    assert body["ok"] is False
    assert isinstance(body["error"], str) and body["error"]
    assert not any(marker in body["error"] for marker in _TRACEBACK_MARKERS)


@pytest.mark.integration
def test_predict_garbage_fasta_is_422(client: TestClient) -> None:
    response = client.post(
        "/predict",
        files={"fasta_file": ("bad.fna", b"not a fasta at all", "text/plain")},
        data={"genome_id": "573.10001"},
    )
    assert response.status_code == 422
    assert response.json()["ok"] is False
