"""Phase B: build the processed dataset (EPIC 1 / issue #13).

Local file I/O only -- no network. Reads the raw flat file(s) fetched by
scripts/fetch_bvbrc_data.py (or the committed test fixtures for a dry run), applies
the pure transforms in genome_firewall.predictor.dataset, and writes:

  data/processed/labels.parquet          -- one row per (genome_id, antibiotic)
  data/processed/ast_lab_rows.parquet    -- pre-collapse, one row per lab measurement
  data/processed/genome_metadata.parquet -- BV-BRC genome metadata incl. MLST
  data/processed/dataset_manifest.json   -- provenance (see dataset.DatasetManifest)

NOTE(EPIC 2): does NOT build feature_matrix.parquet -- that needs AMRFinderPlus,
which runs only via Docker/WSL2 (golden rule #6) and is out of scope for a pure,
network-free data-ingestion script. See issue #17.

NOTE(EPIC 3): does NOT produce train/test splits. predictor/split.py owns the
homology-aware MLST + Mash grouping per ADR-0005, including the Mash fallback for
genomes this script's `genome_metadata.parquet` reports as missing an MLST ST. See
issue #18.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from genome_firewall.constants import KLEBSIELLA_PNEUMONIAE_TAXON_ID
from genome_firewall.predictor import dataset


def _discover_fasta_genome_ids(fasta_dir: Path) -> set[str]:
    """Every genome_id with a non-empty <genome_id>/<genome_id>.fna under
    `fasta_dir` -- the layout scripts/fetch_bvbrc_data.py's fetch-fasta writes."""
    if not fasta_dir.exists():
        return set()
    ids: set[str] = set()
    for child in fasta_dir.iterdir():
        if not child.is_dir():
            continue
        fna = child / f"{child.name}.fna"
        if fna.exists() and fna.stat().st_size > 0:
            ids.add(child.name)
    return ids


def build(
    *,
    flatfile: Path,
    out_dir: Path,
    metadata: Path | None = None,
    fasta_dir: Path | None = None,
    taxon_id: int = KLEBSIELLA_PNEUMONIAE_TAXON_ID,
    evidence_values: tuple[str, ...] = (dataset.LAB_EVIDENCE,),
    require_typing_method: bool = True,
    panel_selected: tuple[str, ...] = (),
    download_cap: int | None = None,
    source_amr_flatfile: str = "PATRIC_genome_AMR.txt",
) -> dataset.DatasetManifest:
    """Run the full Phase-B pipeline and write every output under `out_dir`.

    Returns the manifest (also written as dataset_manifest.json).
    """
    raw_df = dataset.parse_amr_flatfile(flatfile, taxon_id=taxon_id)
    evidence_counts = dataset.enumerate_evidence_values(raw_df)
    sir_counts_raw = dataset.enumerate_sir_values(raw_df)

    lab_rows = dataset.filter_lab_ast(
        raw_df, evidence_values=evidence_values, require_typing_method=require_typing_method
    )
    bundle = dataset.build_labels_bundle(lab_rows)

    genome_metadata = dataset.parse_genome_metadata(metadata, taxon_id=taxon_id) if metadata else None

    fasta_ids = _discover_fasta_genome_ids(fasta_dir) if fasta_dir else set()
    labels = dataset.mark_fasta_availability(bundle.labels, fasta_ids)
    dataset.validate_labels_schema(labels)

    per_drug = dataset.per_drug_label_counts(bundle.working)
    standard_breakdown = dataset.per_drug_standard_breakdown(bundle.working)

    out_dir.mkdir(parents=True, exist_ok=True)
    labels.to_parquet(out_dir / "labels.parquet", index=False)
    bundle.working.to_parquet(out_dir / "ast_lab_rows.parquet", index=False)
    if genome_metadata is not None:
        genome_metadata.to_parquet(out_dir / "genome_metadata.parquet", index=False)

    manifest = dataset.build_manifest(
        labels=labels,
        working=bundle.working,
        dropped_conflicts=bundle.dropped_conflicts,
        raw_rows=raw_df,
        lab_rows=lab_rows,
        genome_metadata=genome_metadata,
        per_drug=per_drug,
        standard_breakdown=standard_breakdown,
        evidence_counts=evidence_counts,
        sir_counts_raw=sir_counts_raw,
        source=dataset.BvbrcSourceInfo(
            ftps_host="ftp.bv-brc.org",
            amr_flatfile=source_amr_flatfile,
            genome_metadata_file="genome_metadata" if metadata else None,
        ),
        taxon_id=taxon_id,
        evidence_values_kept=evidence_values,
        require_typing_method=require_typing_method,
        panel_selected=panel_selected,
        download_cap=download_cap,
    )
    (out_dir / "dataset_manifest.json").write_text(
        json.dumps(manifest.model_dump(), indent=2, default=str), encoding="utf-8"
    )
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Phase B (issue #13): build data/processed/ from the raw BV-BRC flat file. "
        "Local file I/O only -- no network."
    )
    parser.add_argument(
        "--flatfile", required=True, help="Raw PATRIC_genome_AMR flat file (or the committed fixture for a dry run)."
    )
    parser.add_argument("--metadata", help="Raw genome_metadata flat file (optional -- enables MLST coverage).")
    parser.add_argument("--fasta-dir", help="Directory of downloaded genomes/<id>/<id>.fna (sets has_fasta).")
    parser.add_argument("--out-dir", default="data/processed")
    parser.add_argument("--taxon-id", type=int, default=KLEBSIELLA_PNEUMONIAE_TAXON_ID)
    parser.add_argument("--evidence", help="Comma-separated evidence values to keep (default: 'Laboratory Method').")
    parser.add_argument("--no-require-typing-method", action="store_true")
    parser.add_argument(
        "--antibiotics",
        help="Comma-separated finalized panel to record in the manifest (informational -- all drugs are still ingested).",
    )
    parser.add_argument("--cap", type=int, help="Download cap to record in the manifest (informational).")
    args = parser.parse_args(argv)

    evidence_values = (
        tuple(v.strip() for v in args.evidence.split(",")) if args.evidence else (dataset.LAB_EVIDENCE,)
    )
    panel_selected = tuple(a.strip() for a in args.antibiotics.split(",")) if args.antibiotics else ()

    manifest = build(
        flatfile=Path(args.flatfile),
        out_dir=Path(args.out_dir),
        metadata=Path(args.metadata) if args.metadata else None,
        fasta_dir=Path(args.fasta_dir) if args.fasta_dir else None,
        taxon_id=args.taxon_id,
        evidence_values=evidence_values,
        require_typing_method=not args.no_require_typing_method,
        panel_selected=panel_selected,
        download_cap=args.cap,
        source_amr_flatfile=Path(args.flatfile).name,
    )
    print(
        f"Wrote {args.out_dir}/labels.parquet: {manifest.counts.labels_after_collapse} rows, "
        f"{manifest.counts.unique_genomes} unique genomes."
    )
    print(f"Wrote {args.out_dir}/dataset_manifest.json")
    if manifest.counts.dropped_conflict:
        print(
            f"NOTE: {manifest.counts.dropped_conflict} genome x antibiotic pairs dropped "
            "for conflicting SIR calls."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
