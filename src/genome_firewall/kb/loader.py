"""Offline dev tool: distill NCBI ReferenceGeneCatalog rows into extra KB chunks.

Not run in CI (mirrors the AMRFinderPlus runners -- offline/dev only). The committed
hand-curated ``seed/mechanism_chunks.jsonl`` is authoritative; this merely lets a maintainer
grow the corpus from the pinned catalog. The pure row->chunk mapping is unit-tested; the file
orchestration is exercised on a tiny fixture, so nothing here needs the 2.3 MB real catalog.
"""

from __future__ import annotations

import csv
from collections.abc import Mapping
from pathlib import Path

from genome_firewall.kb.corpus import KBChunk

#: AMRFinderPlus Subclass -> the panel drug(s) a gene family is cited against.
_SUBCLASS_TO_DRUGS: dict[str, tuple[str, ...]] = {
    "CARBAPENEM": ("meropenem",),
    "CEPHALOSPORIN": ("ceftriaxone",),
    "QUINOLONE": ("ciprofloxacin",),
    "GENTAMICIN": ("gentamicin",),
    "AMINOGLYCOSIDE": ("gentamicin",),
    "SULFONAMIDE": ("trimethoprim-sulfamethoxazole",),
    "TRIMETHOPRIM": ("trimethoprim-sulfamethoxazole",),
}


def catalog_row_to_chunk(row: Mapping[str, str]) -> KBChunk | None:
    """Map one ReferenceGeneCatalog row to a KBChunk, or ``None`` if it lacks the fields we cite."""
    gene_family = (row.get("gene_family") or "").strip()
    product = (row.get("product_name") or "").strip()
    if not gene_family or not product:
        return None
    subclass = (row.get("subclass") or "").strip().upper()
    return KBChunk(
        chunk_id=f"catalog:{gene_family}",
        gene_family=gene_family,
        drugs=_SUBCLASS_TO_DRUGS.get(subclass, ()),
        text=product,
        source="NCBI Reference Gene Catalog",
    )


def build_catalog_chunks(catalog_path: Path, out_path: Path, *, limit: int | None = None) -> int:
    """Read a tab-separated ReferenceGeneCatalog and write de-duplicated KB chunks as JSONL.

    Returns the number of chunks written. Dev-only helper; never invoked in CI.
    """
    seen: set[str] = set()
    chunks: list[KBChunk] = []
    with catalog_path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        for row in reader:
            chunk = catalog_row_to_chunk(row)
            if chunk is None or chunk.chunk_id in seen:
                continue
            seen.add(chunk.chunk_id)
            chunks.append(chunk)
            if limit is not None and len(chunks) >= limit:
                break
    out_path.write_text("\n".join(c.model_dump_json() for c in chunks) + "\n", encoding="utf-8")
    return len(chunks)
