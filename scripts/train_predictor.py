"""Train + calibrate + conformalize + register every panel drug (issue #22; EPIC 3 PR-B).

Orchestrates the deterministic predictor pipeline over a prebuilt feature matrix:

    feature_matrix.parquet + labels.parquet + genome_metadata.parquet + cached vectors
      -> per drug: binary R/S collapse -> homology-grouped split -> L2-LR + sigmoid calibration
         -> class-conditional split-conformal (fit on the calibration fold, coverage reported
            on the independent test fold) -> save to models/<slug>/v<N>/ + registry.json
      -> all under one MLflow experiment (one run per drug; tracking is crash-safe and OFF the
         verdict path -- see experiment_tracking).

Local, offline of BV-BRC (the matrix was already built by build_feature_matrix.py under
Docker); NEVER runs in CI. ``train_and_register`` is pure-Python and reused by the PR-B
end-to-end test on the synthetic cohort. LLM-free.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping
from pathlib import Path

import numpy as np
import pandas as pd

from genome_firewall.constants import (
    CONFORMAL_ALPHA_GRID,
    DEFAULT_CONFORMAL_ALPHA,
    SUPPORTED_ANTIBIOTICS,
)
from genome_firewall.predictor.calibration import predict_resistant_proba
from genome_firewall.predictor.conformal import (
    ConformalArtifact,
    ConformalEval,
    alpha_sensitivity,
    evaluate_conformal,
    fit_conformal,
)
from genome_firewall.predictor.dataset import canonicalize_antibiotic, collapse_sir_to_binary
from genome_firewall.predictor.experiment_tracking import (
    MLflowTracker,
    NullTracker,
    Tracker,
    default_tracking_uri,
)
from genome_firewall.predictor.model_registry import (
    STATUS_INSUFFICIENT,
    STATUS_TRAINED,
    RegistryEntry,
    save_drug_model,
    write_registry,
)
from genome_firewall.predictor.target_gate import evaluate_gate
from genome_firewall.predictor.train import (
    DEFAULT_TRAINING_CONFIG,
    DrugTrainingResult,
    TrainingConfig,
    train_one_antibiotic,
)
from genome_firewall.schemas import GenomeFeatureVector, ModelFeatureSchema


def binary_labels_for(labels_df: pd.DataFrame, antibiotic: str) -> dict[str, str]:
    """genome_id -> 'R'/'S' for one drug (3-class SIR collapsed per ADR-0017; I/NS/SDD dropped)."""
    canonical = canonicalize_antibiotic(antibiotic)
    drug_rows = labels_df[labels_df["antibiotic"].map(canonicalize_antibiotic) == canonical]
    binary = collapse_sir_to_binary(drug_rows)
    return {
        str(gid): side for gid, side in zip(binary["genome_id"], binary["sir_binary"], strict=True)
    }


def gate_positive_for(
    vectors: Mapping[str, GenomeFeatureVector], antibiotic: str
) -> dict[str, bool]:
    """genome_id -> whether the deterministic gate fires (drives gate-negative headline metrics)."""
    return {gid: evaluate_gate(antibiotic, vector).result.fired for gid, vector in vectors.items()}


def _fold_probabilities(
    matrix: pd.DataFrame, labels_map: Mapping[str, str], result: DrugTrainingResult
) -> tuple[list[float], list[int], list[float], list[int]]:
    """Recompute calibrated P(resistant) on the calibration + test folds. Mirrors
    train_one_antibiotic's genome_id ordering (sorted matrix<->label intersection) so the
    split's positional indices line up."""
    assert result.split.split is not None  # trained => a split exists
    genome_ids = sorted(set(matrix.index) & set(labels_map))
    x = matrix.loc[genome_ids].to_numpy(dtype=np.float64)
    y_int = [1 if labels_map[gid] == "R" else 0 for gid in genome_ids]
    cal_idx = list(result.split.split.calibration_index)
    test_idx = list(result.split.split.test_index)
    p_cal = [float(p) for p in predict_resistant_proba(result.calibrated_model, x[cal_idx])]
    p_test = [float(p) for p in predict_resistant_proba(result.calibrated_model, x[test_idx])]
    return p_cal, [y_int[i] for i in cal_idx], p_test, [y_int[i] for i in test_idx]


def fit_conformal_for_result(
    matrix: pd.DataFrame,
    labels_map: Mapping[str, str],
    result: DrugTrainingResult,
    *,
    alpha: float,
) -> tuple[ConformalArtifact, ConformalEval, tuple[ConformalEval, ...]]:
    """Fit the class-conditional conformal thresholds on the calibration fold; report empirical
    coverage + an alpha-sensitivity table on the INDEPENDENT test fold (the honest check that
    the calibration-fold reuse did not inflate coverage)."""
    p_cal, y_cal, p_test, y_test = _fold_probabilities(matrix, labels_map, result)
    artifact = fit_conformal(p_cal, y_cal, alpha=alpha)
    evaluation = evaluate_conformal(artifact, p_test, y_test)
    sensitivity = alpha_sensitivity(p_cal, y_cal, p_test, y_test, alphas=CONFORMAL_ALPHA_GRID)
    return artifact, evaluation, sensitivity


def _headline(result: DrugTrainingResult) -> dict[str, float | None]:
    metrics = result.metrics
    if metrics is None:
        return {}
    headline = metrics.test_gate_negative or metrics.test_marginal
    if headline is None:
        return {}
    return {
        "n": float(headline.n),
        "resistant_recall": headline.resistant_recall,
        "susceptible_recall": headline.susceptible_recall,
        "balanced_accuracy": headline.balanced_accuracy,
        "auroc": headline.auroc,
        "pr_auc": headline.pr_auc,
        "brier": result.calibration.brier if result.calibration else None,
    }


def train_and_register(
    matrix: pd.DataFrame,
    schema: ModelFeatureSchema,
    labels_df: pd.DataFrame,
    metadata: pd.DataFrame,
    vectors: Mapping[str, GenomeFeatureVector],
    *,
    models_dir: Path,
    alpha: float = DEFAULT_CONFORMAL_ALPHA,
    config: TrainingConfig = DEFAULT_TRAINING_CONFIG,
    tracker: Tracker | None = None,
    antibiotics: tuple[str, ...] = SUPPORTED_ANTIBIOTICS,
) -> dict[str, object]:
    """Train, conformalize, and register every drug; write registry.json. Returns a summary.

    Each trained drug is saved to ``models/<slug>/v<N>/``; an insufficient-data drug is
    recorded in registry.json (status + reason) with no model, so predict.py distinguishes a
    recorded no_call from a missing registry. Reused verbatim by the PR-B e2e test.
    """
    active_tracker: Tracker = tracker if tracker is not None else NullTracker()
    entries: dict[str, RegistryEntry] = {}
    summary: dict[str, object] = {
        "alpha": alpha,
        "amrfinder_db_version": schema.amrfinder_db_version,
        "schema_version": schema.schema_version,
        "n_features": len(schema.feature_names),
        "drugs": {},
    }
    drug_summaries: dict[str, object] = summary["drugs"]  # type: ignore[assignment]

    for antibiotic in antibiotics:
        labels_map = binary_labels_for(labels_df, antibiotic)
        gate_positive = gate_positive_for(vectors, antibiotic)
        result = train_one_antibiotic(
            matrix,
            labels_map,
            metadata,
            antibiotic=antibiotic,
            feature_schema=schema,
            config=config,
            gate_positive=gate_positive,
        )
        active_tracker.start(
            {
                "drug": antibiotic,
                "seed": config.seed,
                "alpha": alpha,
                "split_backend": result.split.backend,
                "n_groups": result.split.n_groups,
                "n_resistant": result.min_n.n_resistant,
                "n_susceptible": result.min_n.n_susceptible,
                "status": result.status,
            }
        )
        if result.status != STATUS_TRAINED:
            entries[antibiotic] = RegistryEntry(
                status=STATUS_INSUFFICIENT, latest_version=None, reason=result.reason
            )
            drug_summaries[antibiotic] = {"status": STATUS_INSUFFICIENT, "reason": result.reason}
            active_tracker.end()
            continue

        artifact, evaluation, sensitivity = fit_conformal_for_result(
            matrix, labels_map, result, alpha=alpha
        )
        version = save_drug_model(models_dir, result, artifact)
        entries[antibiotic] = RegistryEntry(
            status=STATUS_TRAINED, latest_version=version, reason=None
        )
        headline = _headline(result)
        drug_summaries[antibiotic] = {
            "status": STATUS_TRAINED,
            "version": version,
            "best_c": result.best_c,
            "conformal_coverage": evaluation.coverage,
            "no_call_rate": evaluation.no_call_rate,
            "conformal_guarantee_available": artifact.guarantee_available,
            "alpha_sensitivity": [
                {"alpha": ev.alpha, "coverage": ev.coverage, "no_call_rate": ev.no_call_rate}
                for ev in sensitivity
            ],
            **headline,
        }
        active_tracker.log_metrics(
            {
                key: float(value)
                for key, value in {
                    **headline,
                    "conformal_coverage": evaluation.coverage,
                    "no_call_rate": evaluation.no_call_rate,
                }.items()
                if value is not None
            }
        )
        card = models_dir / _drug_dir_name(antibiotic, version)
        active_tracker.log_artifact(card / "model_card.md")
        active_tracker.log_artifact(card / "metrics.json")
        active_tracker.end()

    write_registry(models_dir, entries, base_schema=schema)
    return summary


def _drug_dir_name(antibiotic: str, version: str) -> str:
    from genome_firewall.predictor.model_registry import drug_slug

    return f"{drug_slug(antibiotic)}/{version}"


def _load_vectors(cache_dir: Path) -> dict[str, GenomeFeatureVector]:
    return {
        path.stem: GenomeFeatureVector.model_validate_json(path.read_text(encoding="utf-8"))
        for path in sorted(cache_dir.glob("*.json"))
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Train + register the per-drug predictors (PR-B).")
    parser.add_argument("--processed-dir", default="data/processed")
    parser.add_argument("--metadata", default="data/processed/genome_metadata.parquet")
    parser.add_argument("--labels", default="data/processed/labels.parquet")
    parser.add_argument("--vectors-dir", default="data/interim/genome_vectors")
    parser.add_argument("--models-dir", default="models")
    parser.add_argument("--alpha", type=float, default=DEFAULT_CONFORMAL_ALPHA)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--no-tracking", action="store_true", help="skip MLflow (use NullTracker)")
    args = parser.parse_args(argv)

    processed = Path(args.processed_dir)
    matrix = pd.read_parquet(processed / "feature_matrix.parquet")
    matrix.index = matrix.index.astype(str)
    schema = ModelFeatureSchema.model_validate_json(
        (processed / "feature_schema.json").read_text(encoding="utf-8")
    )
    labels_df = pd.read_parquet(args.labels)
    metadata = pd.read_parquet(args.metadata)
    vectors = _load_vectors(Path(args.vectors_dir))
    if not vectors:
        print(f"No cached vectors under {args.vectors_dir}; run build_feature_matrix.py first.")
        return 1

    tracker: Tracker = (
        NullTracker()
        if args.no_tracking
        else MLflowTracker(default_tracking_uri(Path.cwd()), log=lambda m: print(m, flush=True))
    )
    config = TrainingConfig(seed=args.seed)
    models_dir = Path(args.models_dir)
    summary = train_and_register(
        matrix,
        schema,
        labels_df,
        metadata,
        vectors,
        models_dir=models_dir,
        alpha=args.alpha,
        config=config,
        tracker=tracker,
    )
    (models_dir / "results_summary.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    drugs = summary["drugs"]
    assert isinstance(drugs, dict)
    trained = sum(1 for d in drugs.values() if d.get("status") == STATUS_TRAINED)  # type: ignore[union-attr]
    print(f"Trained {trained}/{len(drugs)} drugs -> {models_dir}/ (summary: results_summary.json)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
