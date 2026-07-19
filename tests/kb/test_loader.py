"""Unit tests for the offline catalog distiller (dev-only helper)."""

from __future__ import annotations

from pathlib import Path

from genome_firewall.kb.corpus import load_corpus
from genome_firewall.kb.loader import build_catalog_chunks, catalog_row_to_chunk


def test_row_maps_subclass_to_drugs() -> None:
    chunk = catalog_row_to_chunk(
        {"gene_family": "blaKPC", "product_name": "KPC carbapenemase", "subclass": "CARBAPENEM"}
    )
    assert chunk is not None
    assert chunk.chunk_id == "catalog:blaKPC"
    assert chunk.drugs == ("meropenem",)
    assert chunk.source == "NCBI Reference Gene Catalog"


def test_row_without_gene_family_or_product_is_skipped() -> None:
    assert catalog_row_to_chunk({"gene_family": "", "product_name": "x"}) is None
    assert catalog_row_to_chunk({"gene_family": "g", "product_name": ""}) is None


def test_build_catalog_chunks_writes_deduped_jsonl(tmp_path: Path) -> None:
    catalog = tmp_path / "catalog.txt"
    catalog.write_text(
        "gene_family\tproduct_name\tsubclass\n"
        "blaKPC\tKPC carbapenemase\tCARBAPENEM\n"
        "blaKPC\tKPC carbapenemase dup\tCARBAPENEM\n"  # duplicate gene_family -> deduped
        "sul1\tdihydropteroate synthase\tSULFONAMIDE\n",
        encoding="utf-8",
    )
    out = tmp_path / "catalog_chunks.jsonl"
    written = build_catalog_chunks(catalog, out)
    assert written == 2
    corpus = load_corpus(tmp_path)
    assert {c.chunk_id for c in corpus} == {"catalog:blaKPC", "catalog:sul1"}


def test_build_catalog_chunks_respects_limit(tmp_path: Path) -> None:
    catalog = tmp_path / "catalog.txt"
    catalog.write_text(
        "gene_family\tproduct_name\tsubclass\na\tprod a\tCARBAPENEM\nb\tprod b\tSULFONAMIDE\n",
        encoding="utf-8",
    )
    assert build_catalog_chunks(catalog, tmp_path / "o.jsonl", limit=1) == 1
