"""Unit tests for the deterministic narrative renderer."""

from __future__ import annotations

from genome_firewall.constants import LAB_CONFIRMATION_DISCLAIMER, SUPPORTED_ANTIBIOTICS
from genome_firewall.report.builder import build_report
from genome_firewall.report.narrative import render_deterministic_narrative
from tests.report.conftest import make_prediction_inputs


def _narrative() -> str:
    return render_deterministic_narrative(build_report(make_prediction_inputs()))


def test_narrative_ends_with_the_exact_disclaimer() -> None:
    assert _narrative().endswith(LAB_CONFIRMATION_DISCLAIMER)


def test_narrative_renders_no_call_literally_never_softened() -> None:
    text = _narrative()
    assert "NO CALL" in text
    assert "probably" not in text.lower()


def test_narrative_orders_drugs_by_the_supported_panel() -> None:
    text = _narrative()
    positions = [text.find(f"{drug}:") for drug in SUPPORTED_ANTIBIOTICS if f"{drug}:" in text]
    assert positions == sorted(positions)


def test_narrative_is_deterministic_across_runs() -> None:
    assert _narrative() == _narrative()


def test_narrative_shows_known_mechanism_evidence() -> None:
    text = _narrative()
    assert "blaKPC-2" in text
    assert "known resistance mechanism" in text
