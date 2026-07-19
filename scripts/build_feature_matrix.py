"""Batch AMRFinderPlus feature-matrix builder for the EPIC 3 real training run (issue #18).

Docker/WSL2 + local file I/O only -- NEVER runs in CI (golden rule #6). For each downloaded
genome FASTA it runs AMRFinderPlus (annotation/), pivots to a GenomeFeatureVector (reader/),
and caches the per-genome vector JSON so re-runs skip finished genomes (idempotent/resumable);
then it freezes the ordered vocabulary (features/vocabulary) and writes
data/processed/feature_matrix.parquet plus the base ModelFeatureSchema and a build manifest.

The pure pieces (build_genome_vectors via MockAnnotator, build_feature_matrix) are exercised
offline in tests/scripts/test_build_feature_matrix.py; only DockerAnnotator touches Docker.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Protocol

import pandas as pd

from genome_firewall.annotation.amrfinder import PINNED_DB_VERSION, run_amrfinder
from genome_firewall.features.feature_matrix import assemble_feature_matrix
from genome_firewall.features.vocabulary import build_vocabulary
from genome_firewall.reader.feature_builder import ReferenceGeneCatalog, build_feature_vector
from genome_firewall.schemas import AnnotationResult, GenomeFeatureVector, ModelFeatureSchema


class Annotator(Protocol):
    """Anything that turns a FASTA into an AnnotationResult (run_amrfinder or MockAnnotator)."""

    def annotate(self, fasta_path: Path, *, genome_id: str) -> AnnotationResult: ...


class DockerAnnotator:
    """Adapts annotation.amrfinder.run_amrfinder to the Annotator protocol (Docker/WSL2)."""

    def __init__(self, *, organism: str = "Klebsiella_pneumoniae", threads: int = 4) -> None:
        self._organism = organism
        self._threads = threads

    def annotate(self, fasta_path: Path, *, genome_id: str) -> AnnotationResult:
        return run_amrfinder(
            fasta_path, genome_id=genome_id, organism=self._organism, threads=self._threads
        )


def build_genome_vectors(
    fasta_paths: dict[str, Path],
    annotator: Annotator,
    catalog: ReferenceGeneCatalog,
    *,
    cache_dir: Path | None = None,
) -> tuple[list[GenomeFeatureVector], list[str]]:
    """Annotate each genome -> GenomeFeatureVector, caching vector JSON so a re-run skips
    genomes already done. Returns (vectors, failures). Deterministic genome order."""
    vectors: list[GenomeFeatureVector] = []
    failures: list[str] = []
    for genome_id in sorted(fasta_paths):
        cache_path = (cache_dir / f"{genome_id}.json") if cache_dir is not None else None
        if cache_path is not None and cache_path.exists():
            vectors.append(
                GenomeFeatureVector.model_validate_json(cache_path.read_text(encoding="utf-8"))
            )
            continue
        result = annotator.annotate(fasta_paths[genome_id], genome_id=genome_id)
        if not result.ok or result.data is None:
            failures.append(f"{genome_id}: {result.error}")
            continue
        vector = build_feature_vector(
            genome_id,
            result.data,
            amrfinder_db_version=result.amrfinder_db_version or PINNED_DB_VERSION,
            catalog=catalog,
        )
        if cache_path is not None:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(vector.model_dump_json(indent=2), encoding="utf-8")
        vectors.append(vector)
    return vectors, failures


def build_feature_matrix(
    vectors: list[GenomeFeatureVector], *, amrfinder_db_version: str = PINNED_DB_VERSION
) -> tuple[pd.DataFrame, ModelFeatureSchema]:
    """Freeze the vocabulary over the cohort and assemble the numeric feature matrix."""
    schema = build_vocabulary(vectors, amrfinder_db_version=amrfinder_db_version)
    matrix = assemble_feature_matrix(vectors, schema)
    return matrix, schema


def discover_fastas(genomes_dir: Path) -> dict[str, Path]:
    """genome_id -> FASTA path from data/raw/bvbrc/genomes/<id>/<id>.fna."""
    return {path.stem: path for path in sorted(genomes_dir.glob("*/*.fna"))}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Batch AMRFinderPlus feature-matrix builder (EPIC 3; Docker/WSL2 only)."
    )
    parser.add_argument("--genomes-dir", default="data/raw/bvbrc/genomes")
    parser.add_argument("--catalog", default="data/reference/ReferenceGeneCatalog.txt")
    parser.add_argument("--out-dir", default="data/processed")
    parser.add_argument("--cache-dir", default="data/interim/genome_vectors")
    parser.add_argument("--threads", type=int, default=4)
    args = parser.parse_args(argv)

    genomes_dir = Path(args.genomes_dir)
    fasta_paths = discover_fastas(genomes_dir)
    if not fasta_paths:
        print(f"No FASTAs under {genomes_dir} (expected <id>/<id>.fna). Run fetch-fasta first.")
        return 1
    catalog = ReferenceGeneCatalog(Path(args.catalog))
    annotator = DockerAnnotator(threads=args.threads)
    print(f"Annotating {len(fasta_paths)} genome(s) via Docker AMRFinderPlus...")
    vectors, failures = build_genome_vectors(
        fasta_paths, annotator, catalog, cache_dir=Path(args.cache_dir)
    )
    for failure in failures:
        print(f"  FAILED {failure}")
    if not vectors:
        print("No genomes annotated successfully; aborting.")
        return 1

    matrix, schema = build_feature_matrix(vectors)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    matrix_path = out_dir / "feature_matrix.parquet"
    matrix.to_parquet(matrix_path)
    (out_dir / "feature_schema.json").write_text(schema.model_dump_json(indent=2), encoding="utf-8")
    manifest = {
        "genomes_annotated": len(vectors),
        "genomes_failed": len(failures),
        "n_features": len(schema.feature_names),
        "amrfinder_db_version": schema.amrfinder_db_version,
        "vocabulary_sha256": schema.vocabulary_sha256,
    }
    (out_dir / "feature_matrix_manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    print(
        f"Feature matrix: {matrix.shape[0]} genomes x {matrix.shape[1]} features -> {matrix_path} "
        f"({len(failures)} genome(s) failed)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
