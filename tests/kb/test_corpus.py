"""Unit tests for the KB corpus loader."""

from __future__ import annotations

from pathlib import Path

from genome_firewall.kb.corpus import KBChunk, load_corpus


def test_seed_corpus_loads_and_is_well_formed() -> None:
    corpus = load_corpus()
    assert len(corpus) >= 15
    ids = {c.chunk_id for c in corpus}
    assert {"kpc", "armA_rmt", "sul", "gyra_qrdr"} <= ids
    for chunk in corpus:
        assert chunk.text
        assert chunk.source  # provenance is mandatory (golden rule #3)
        assert chunk.gene_family


def test_load_corpus_dedupes_by_chunk_id(tmp_path: Path) -> None:
    (tmp_path / "a.jsonl").write_text(
        '{"chunk_id":"x","gene_family":"g","drugs":[],"text":"first","source":"s"}\n',
        encoding="utf-8",
    )
    (tmp_path / "b.jsonl").write_text(
        '{"chunk_id":"x","gene_family":"g","drugs":[],"text":"second","source":"s"}\n'
        "\n",  # blank line tolerated
        encoding="utf-8",
    )
    corpus = load_corpus(tmp_path)
    assert len(corpus) == 1
    assert corpus[0].text == "first"  # sorted filename order: a.jsonl wins


def test_kbchunk_forbids_extra_fields() -> None:
    chunk = KBChunk(chunk_id="c", gene_family="g", text="t", source="s")
    assert chunk.drugs == ()
