"""Scaffold smoke tests.

At EPIC-0 the packages are skeletons. These tests assert the two things that must
hold from the first commit: the package tree imports cleanly, and the structurally
enforced constants (disclaimer text, supported species/antibiotics, version source
of truth) are present and well-formed. Later EPICs add behavioural tests alongside
these; the end-to-end integration-test shapes live in
Documentation/08-crosscutting-concepts/README.md.
"""

from __future__ import annotations

import importlib

import genome_firewall
from genome_firewall import constants

_SUBPACKAGES = (
    "annotation",
    "api",
    "eval",
    "features",
    "kb",
    "llm",
    "predictor",
    "reader",
    "report",
    "ui",
)


def test_version_is_single_sourced() -> None:
    """__version__ is the single source of truth (pyproject reads it via hatch)."""
    assert isinstance(genome_firewall.__version__, str)
    assert genome_firewall.__version__.count(".") >= 2


def test_all_subpackages_import() -> None:
    """Every declared subpackage is importable — the skeleton stays wired up."""
    for name in _SUBPACKAGES:
        module = importlib.import_module(f"genome_firewall.{name}")
        assert module is not None


def test_disclaimer_constant_is_present_and_meaningful() -> None:
    """The lab-confirmation disclaimer is non-empty and names lab testing."""
    text = constants.LAB_CONFIRMATION_DISCLAIMER
    assert isinstance(text, str) and text.strip()
    assert "laboratory" in text.lower()


def test_supported_panels_are_nonempty_tuples() -> None:
    assert constants.SUPPORTED_SPECIES == ("Klebsiella pneumoniae",)
    assert len(constants.SUPPORTED_ANTIBIOTICS) == 5
    assert all(isinstance(drug, str) and drug for drug in constants.SUPPORTED_ANTIBIOTICS)
