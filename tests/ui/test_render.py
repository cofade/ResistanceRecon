"""Unit coverage for the pure ui/render.py helpers (issue #28): the ALLOW/BLOCK/REVIEW mapping,
the KNOWN-vs-STATISTICAL badges, the firewall-row projection off a built report, and the
mandatory disclaimer text. No Streamlit import here (render.py is deliberately Streamlit-free).
"""

from __future__ import annotations

import pytest

from genome_firewall.constants import LAB_CONFIRMATION_DISCLAIMER, SUPPORTED_ANTIBIOTICS
from genome_firewall.schemas import Verdict
from genome_firewall.ui import render
from tests._demo import demo_report


@pytest.mark.parametrize(
    ("verdict", "label", "color"),
    [
        ("likely_to_work", "ALLOW", "green"),
        ("likely_to_fail", "BLOCK", "red"),
        ("no_call", "REVIEW", "orange"),
    ],
)
def test_verdict_style(verdict: Verdict, label: str, color: str) -> None:
    assert render.verdict_style(verdict) == (label, color)


def test_evidence_badges_distinguish_known_from_statistical() -> None:
    assert render.evidence_badge("known_mechanism") == "KNOWN MECHANISM"
    assert render.evidence_badge("statistical_association") == "STATISTICAL SIGNAL"
    assert render.evidence_badge("no_signal") == "NO SIGNAL"


def test_firewall_rows_project_every_panel_drug() -> None:
    rows = render.firewall_rows(demo_report("573.10001"))

    assert tuple(r.antibiotic for r in rows) == SUPPORTED_ANTIBIOTICS
    assert all(r.label in {"ALLOW", "BLOCK", "REVIEW"} for r in rows)
    assert all(0.0 <= r.confidence_pct <= 100.0 for r in rows)
    # ciprofloxacin's gate fires on this genome -> BLOCK + KNOWN MECHANISM badge.
    cipro = next(r for r in rows if r.antibiotic == "ciprofloxacin")
    assert cipro.label == "BLOCK"
    assert cipro.evidence_badge == "KNOWN MECHANISM"


def test_evidence_lines_pair_description_with_source() -> None:
    report = demo_report("573.10001")
    cipro = next(p for p in report.predictions if p.antibiotic == "ciprofloxacin")
    lines = render.evidence_lines(cipro)
    assert lines and all(" — " in line for line in lines)


def test_disclaimer_text_is_the_canonical_constant() -> None:
    assert render.disclaimer_text() == LAB_CONFIRMATION_DISCLAIMER
