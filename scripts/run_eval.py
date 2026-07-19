"""Evaluate the trained registry on held-out folds -> models/eval_summary.json (EPIC 7 / #29).

Dev/offline only. Re-scoring needs the feature matrix under ``data/processed/`` (gitignored),
so this NEVER runs in CI -- exactly like ``scripts/train_predictor.py``. CI coverage of the
mechanics comes from the synthetic-cohort integration test; this script only wires the
prebuilt real artifacts into ``genome_firewall.eval.evaluate_registry`` and writes the report.
Mirrors ``train_predictor.main``'s argument surface so it consumes the same inputs. LLM-free.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from genome_firewall.constants import DEFAULT_CONFORMAL_ALPHA
from genome_firewall.eval.runner import evaluate_registry
from genome_firewall.predictor.model_registry import PredictorRegistry
from genome_firewall.schemas import GenomeFeatureVector


def _load_vectors(cache_dir: Path) -> dict[str, GenomeFeatureVector]:
    return {
        path.stem: GenomeFeatureVector.model_validate_json(path.read_text(encoding="utf-8"))
        for path in sorted(cache_dir.glob("*.json"))
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Evaluate trained predictors on held-out folds (EPIC 7)."
    )
    parser.add_argument("--processed-dir", default="data/processed")
    parser.add_argument("--metadata", default="data/processed/genome_metadata.parquet")
    parser.add_argument("--labels", default="data/processed/labels.parquet")
    parser.add_argument("--vectors-dir", default="data/interim/genome_vectors")
    parser.add_argument("--models-dir", default="models")
    parser.add_argument(
        "--out", default=None, help="output path (default: <models-dir>/eval_summary.json)"
    )
    parser.add_argument("--alpha", type=float, default=DEFAULT_CONFORMAL_ALPHA)
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args(argv)

    processed = Path(args.processed_dir)
    matrix = pd.read_parquet(processed / "feature_matrix.parquet")
    matrix.index = matrix.index.astype(str)
    labels_df = pd.read_parquet(args.labels)
    metadata = pd.read_parquet(args.metadata)
    vectors = _load_vectors(Path(args.vectors_dir))
    if not vectors:
        print(f"No cached vectors under {args.vectors_dir}; run build_feature_matrix.py first.")
        return 1

    models_dir = Path(args.models_dir)
    registry = PredictorRegistry.load(models_dir)
    report = evaluate_registry(
        registry,
        matrix,
        labels_df,
        metadata,
        vectors,
        models_dir=models_dir,
        alpha=args.alpha,
        seed=args.seed,
    )
    out = Path(args.out) if args.out else models_dir / "eval_summary.json"
    out.write_text(report.model_dump_json(indent=2), encoding="utf-8")

    diverged = [
        drug
        for drug, metrics in report.drugs.items()
        if metrics.reproducibility.committed_match is False
    ]
    print(f"Evaluated {len(report.drugs)} drug(s), skipped {len(report.skipped)} -> {out}")
    if diverged:
        print(
            f"WARNING: reproduction cross-check FAILED for {diverged} -- the reproduced split "
            "diverged from the committed metrics; do NOT ship these numbers."
        )
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
