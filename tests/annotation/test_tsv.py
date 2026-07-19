"""Unit tests for annotation._tsv (issue #16) -- the shared TSV parser used by both
MockAnnotator and the real Docker runner."""

from __future__ import annotations

from pathlib import Path

from genome_firewall.annotation._tsv import parse_amrfinder_tsv

_FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "amrfinder"


def test_parses_rich_fixture() -> None:
    features = parse_amrfinder_tsv(_FIXTURE_DIR / "573.10001.tsv")
    assert len(features) == 9
    gene_symbols = [f.gene_symbol for f in features]
    assert gene_symbols.count("blaTEM-1") == 2, "near-duplicate hits must not be deduplicated"


def test_parses_point_disrupt_row() -> None:
    features = parse_amrfinder_tsv(_FIXTURE_DIR / "573.10001.tsv")
    ompk35 = next(f for f in features if f.gene_symbol == "ompK35_K292QfsTer17")
    assert ompk35.element_subtype == "POINT_DISRUPT"
    assert ompk35.method == "POINTX"
    assert ompk35.drug_class == "BETA-LACTAM"


def test_na_columns_become_none() -> None:
    features = parse_amrfinder_tsv(_FIXTURE_DIR / "573.10001.tsv")
    fief = next(f for f in features if f.gene_symbol == "fieF")
    assert fief.drug_class is None
    assert fief.drug_subclass is None


def test_parses_empty_fixture() -> None:
    assert parse_amrfinder_tsv(_FIXTURE_DIR / "573.10002.tsv") == ()


def test_parses_synthesized_edge_cases() -> None:
    features = parse_amrfinder_tsv(_FIXTURE_DIR / "573.10003.tsv")
    methods = {f.gene_symbol: f.method for f in features}
    assert methods["blaKPC-3"] == "PARTIAL_CONTIG_ENDX"
    assert methods["ydgH-like"] == "HMM"
    unmapped = next(f for f in features if f.gene_symbol == "newGene-1")
    assert unmapped.element_subtype == "AMR"
    assert unmapped.drug_class is None
