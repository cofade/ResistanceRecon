# AMR-mechanism KB seed corpus

Provenance and scope for the committed evidence-RAG corpus.

## Files

- **`mechanism_chunks.jsonl`** — hand-curated, one `KBChunk` per line
  (`chunk_id`, `gene_family`, `drugs`, `text`, `source`). This is the authoritative MVP
  corpus and is always present in CI. It covers the resistance-mechanism families for the five
  panel antibiotics (carbapenemases, ESBL/AmpC, QRDR/PMQR, RMTase/AME, sul/dfr) plus the
  narrow-spectrum SHV distinction.
- **`catalog_chunks.jsonl`** *(optional, dev-generated)* — additional chunks distilled from
  `data/reference/ReferenceGeneCatalog.txt` by `kb/loader.build_catalog_chunks()`. Not required
  for CI; `load_corpus()` merges it when present.

## Curation basis

The chunk texts restate well-established AMR facts sourced from this repo's research findings
(`Documentation/research-findings/antibiotic-panel.md`) and the standard curated references it
cites (NCBI Reference Gene Catalog / NDARO, CARD ARO, EUCAST Expert Rules). Each chunk records
its `source`. This is a deliberately small MVP corpus — see the ADR-0019 limitation note: a thin
KB under-cites some mechanisms, which is stated honestly rather than hidden.

## Retrieval-only

The corpus is used **only** to enrich the LLM narrative with citations. It never sets an
`evidence_category` and never decides a verdict — the KNOWN_MECHANISM tag is set deterministically
by `report/evidence.py` from `features/mechanisms.py` membership (ADR-0020), not by retrieval.

## Re-validation

Periodically re-check the gene→drug mechanism statements against the current NCBI Reference Gene
Catalog / CARD releases, mirroring the fixture re-validation discipline in
`tests/fixtures/amrfinder/README.md`.
