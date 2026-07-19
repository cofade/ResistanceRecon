"""Filesystem model registry: persist + load per-drug trained models (issue #22).

Layout under ``models/`` (small text artifacts are committed; ``*.joblib`` is gitignored):

    models/
      registry.json                    # per-drug status + the base annotation/schema versions
      <drug-slug>/
        v1/
          calibrated_model.joblib      # the sklearn CalibratedClassifierCV (gitignored)
          feature_schema.json          # ModelFeatureSchema -- the ordered vocabulary contract
          conformal.json               # ConformalArtifact -- the class-conditional thresholds
          coefficients.json            # signed L2-LR weights (statistical-association evidence)
          metrics.json                 # DrugMetrics (marginal + gate-negative + holdout)
          model_card.md                # human-readable per-drug card

``registry.json`` records, per drug, ``status = trained | insufficient_data`` and the
``latest_version``, so predict.py distinguishes an insufficient-data no_call (a real,
recorded outcome) from a missing-model error (a registry that was never built). The
registry's top-level annotation/schema versions are the compatibility contract predict.py
validates an incoming genome against. Pure filesystem + Pydantic; LLM-free.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import joblib

from genome_firewall.predictor.conformal import ConformalArtifact
from genome_firewall.predictor.train import DrugTrainingResult, SignedCoefficient
from genome_firewall.schemas import ModelFeatureSchema

REGISTRY_SCHEMA = "predictor-registry/1"
REGISTRY_FILE = "registry.json"
_MODEL_FILE = "calibrated_model.joblib"
_SCHEMA_FILE = "feature_schema.json"
_CONFORMAL_FILE = "conformal.json"
_COEF_FILE = "coefficients.json"
_METRICS_FILE = "metrics.json"
_CARD_FILE = "model_card.md"

STATUS_TRAINED = "trained"
STATUS_INSUFFICIENT = "insufficient_data"


def drug_slug(antibiotic: str) -> str:
    """Filesystem-safe per-drug directory name (``trimethoprim-sulfamethoxazole`` stays that)."""
    return re.sub(r"[^a-z0-9]+", "-", antibiotic.lower()).strip("-")


@dataclass(frozen=True)
class DrugModel:
    """One drug's loaded, ready-to-serve model bundle."""

    antibiotic: str
    version: str
    calibrated_model: Any  # sklearn CalibratedClassifierCV; joblib-persisted
    feature_schema: ModelFeatureSchema
    conformal: ConformalArtifact
    coefficients: tuple[SignedCoefficient, ...]

    @property
    def alpha(self) -> float:
        return self.conformal.alpha


@dataclass(frozen=True)
class RegistryEntry:
    """Per-drug status line in registry.json."""

    status: str
    latest_version: str | None = None
    reason: str | None = None


@dataclass
class PredictorRegistry:
    """All per-drug statuses + the trained models, plus the base compatibility contract."""

    amrfinder_db_version: str | None
    schema_version: str | None
    engineered_feature_spec_version: str | None
    entries: dict[str, RegistryEntry]
    drugs: dict[str, DrugModel]

    def status(self, antibiotic: str) -> str | None:
        entry = self.entries.get(antibiotic)
        return entry.status if entry is not None else None

    def reason(self, antibiotic: str) -> str | None:
        entry = self.entries.get(antibiotic)
        return entry.reason if entry is not None else None

    def get(self, antibiotic: str) -> DrugModel | None:
        return self.drugs.get(antibiotic)

    @classmethod
    def load(cls, models_dir: str | Path) -> PredictorRegistry:
        """Load registry.json and every trained drug model under ``models_dir``."""
        root = Path(models_dir)
        manifest = json.loads((root / REGISTRY_FILE).read_text(encoding="utf-8"))
        entries: dict[str, RegistryEntry] = {}
        drugs: dict[str, DrugModel] = {}
        for antibiotic, record in manifest.get("drugs", {}).items():
            entry = RegistryEntry(
                status=record["status"],
                latest_version=record.get("latest_version"),
                reason=record.get("reason"),
            )
            entries[antibiotic] = entry
            if entry.status == STATUS_TRAINED and entry.latest_version is not None:
                drugs[antibiotic] = load_drug_model(root, antibiotic, version=entry.latest_version)
        return cls(
            amrfinder_db_version=manifest.get("amrfinder_db_version"),
            schema_version=manifest.get("schema_version"),
            engineered_feature_spec_version=manifest.get("engineered_feature_spec_version"),
            entries=entries,
            drugs=drugs,
        )


def _version_number(name: str) -> int:
    match = re.fullmatch(r"v(\d+)", name)
    return int(match.group(1)) if match else -1


def _next_version(drug_dir: Path) -> str:
    """``v<N+1>`` where N is the highest existing version dir, or ``v1`` if none."""
    if not drug_dir.exists():
        return "v1"
    existing = [_version_number(p.name) for p in drug_dir.iterdir() if p.is_dir()]
    highest = max((n for n in existing if n >= 1), default=0)
    return f"v{highest + 1}"


def latest_version(models_dir: str | Path, antibiotic: str) -> str | None:
    """Highest ``v<N>`` directory for a drug, or None if it has never been trained."""
    drug_dir = Path(models_dir) / drug_slug(antibiotic)
    if not drug_dir.exists():
        return None
    versions = sorted(
        (p.name for p in drug_dir.iterdir() if p.is_dir() and _version_number(p.name) >= 1),
        key=_version_number,
    )
    return versions[-1] if versions else None


def _resolve_version_dir(drug_dir: Path, version: str) -> Path:
    if version == "latest":
        resolved = latest_version(drug_dir.parent, drug_dir.name)
        if resolved is None:
            raise FileNotFoundError(f"no trained versions under {drug_dir}")
        return drug_dir / resolved
    return drug_dir / version


def save_drug_model(
    models_dir: str | Path,
    result: DrugTrainingResult,
    conformal: ConformalArtifact,
    *,
    version: str | None = None,
) -> str:
    """Persist one trained drug's model bundle; returns the version written (``v<N>``).

    Raises ValueError if the result is not a trained model (insufficient_data results carry
    no model and are recorded only in registry.json, never saved here).
    """
    if result.status != STATUS_TRAINED or result.calibrated_model is None:
        raise ValueError(f"cannot save a non-trained result for {result.antibiotic!r}")
    if result.feature_schema is None:
        raise ValueError(f"trained result for {result.antibiotic!r} is missing its feature_schema")
    drug_dir = Path(models_dir) / drug_slug(result.antibiotic)
    resolved = version or _next_version(drug_dir)
    version_dir = drug_dir / resolved
    version_dir.mkdir(parents=True, exist_ok=True)

    joblib.dump(result.calibrated_model, version_dir / _MODEL_FILE)
    (version_dir / _SCHEMA_FILE).write_text(
        result.feature_schema.model_dump_json(indent=2), encoding="utf-8"
    )
    (version_dir / _CONFORMAL_FILE).write_text(
        conformal.model_dump_json(indent=2), encoding="utf-8"
    )
    (version_dir / _COEF_FILE).write_text(
        json.dumps([c.model_dump() for c in result.coefficients], indent=2), encoding="utf-8"
    )
    if result.metrics is not None:
        (version_dir / _METRICS_FILE).write_text(
            result.metrics.model_dump_json(indent=2), encoding="utf-8"
        )
    (version_dir / _CARD_FILE).write_text(
        render_model_card(result, conformal, version=resolved), encoding="utf-8"
    )
    return resolved


def load_drug_model(
    models_dir: str | Path, antibiotic: str, *, version: str = "latest"
) -> DrugModel:
    """Load one drug's model bundle (``version='latest'`` resolves the highest ``v<N>``)."""
    drug_dir = Path(models_dir) / drug_slug(antibiotic)
    version_dir = _resolve_version_dir(drug_dir, version)
    model = joblib.load(version_dir / _MODEL_FILE)
    schema = ModelFeatureSchema.model_validate_json(
        (version_dir / _SCHEMA_FILE).read_text(encoding="utf-8")
    )
    conformal = ConformalArtifact.model_validate_json(
        (version_dir / _CONFORMAL_FILE).read_text(encoding="utf-8")
    )
    coefficients = tuple(
        SignedCoefficient(**record)
        for record in json.loads((version_dir / _COEF_FILE).read_text(encoding="utf-8"))
    )
    return DrugModel(
        antibiotic=antibiotic,
        version=version_dir.name,
        calibrated_model=model,
        feature_schema=schema,
        conformal=conformal,
        coefficients=coefficients,
    )


def write_registry(
    models_dir: str | Path,
    entries: dict[str, RegistryEntry],
    *,
    base_schema: ModelFeatureSchema | None = None,
) -> Path:
    """Write registry.json: per-drug status + the base compatibility versions predict.py
    validates incoming genomes against. ``base_schema`` supplies those versions (all trained
    drugs share one base vocabulary in a run); None leaves them absent (compat check skipped).
    """
    root = Path(models_dir)
    root.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, Any] = {
        "registry_schema": REGISTRY_SCHEMA,
        "amrfinder_db_version": base_schema.amrfinder_db_version if base_schema else None,
        "schema_version": base_schema.schema_version if base_schema else None,
        "engineered_feature_spec_version": (
            base_schema.engineered_feature_spec_version if base_schema else None
        ),
        "drugs": {
            antibiotic: {
                "status": entry.status,
                "latest_version": entry.latest_version,
                "reason": entry.reason,
            }
            for antibiotic, entry in entries.items()
        },
    }
    path = root / REGISTRY_FILE
    path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return path


def _fmt(value: float | None, digits: int = 3) -> str:
    return "n/a" if value is None else f"{value:.{digits}f}"


def render_model_card(
    result: DrugTrainingResult, conformal: ConformalArtifact, *, version: str
) -> str:
    """A concise per-drug model card (headline gate-negative metrics + conformal behaviour)."""
    lines = [
        f"# Model card -- {result.antibiotic} ({version})",
        "",
        "Per-antibiotic L2 logistic regression + sigmoid calibration + class-conditional "
        "(Mondrian) split-conformal. **Decision support only -- confirm every result with "
        "standard laboratory antimicrobial susceptibility testing.**",
        "",
        "## Provenance",
        f"- status: **{result.status}**",
        f"- best C: {result.best_c}",
        f"- min-n gate: {result.min_n.n_resistant} R / {result.min_n.n_susceptible} S "
        f"(ok={result.min_n.ok})",
        f"- homology groups: {result.split.n_groups} (backend {result.split.backend}, "
        f"seed {result.split.seed}); split degraded={result.split.degraded}",
    ]
    metrics = result.metrics
    headline = metrics.test_gate_negative or metrics.test_marginal if metrics else None
    if headline is not None:
        lines += [
            "",
            "## Headline metrics (gate-negative test fold -- the population the model serves)",
            f"- n: {headline.n} ({headline.n_resistant} R / {headline.n_susceptible} S)",
            f"- resistant recall: {_fmt(headline.resistant_recall)}",
            f"- susceptible recall: {_fmt(headline.susceptible_recall)}",
            f"- balanced accuracy: {_fmt(headline.balanced_accuracy)}",
            f"- AUROC: {_fmt(headline.auroc)} | PR-AUC: {_fmt(headline.pr_auc)}",
        ]
    if result.calibration is not None:
        lines += ["", "## Calibration", f"- Brier score: {_fmt(result.calibration.brier)}"]
    lines += [
        "",
        "## Conformal (no-call) behaviour",
        f"- alpha: {conformal.alpha}",
        f"- tau_s: {_fmt(conformal.tau_s)} | tau_r: {_fmt(conformal.tau_r)}",
        f"- calibration counts: {conformal.n_cal_susceptible} S / {conformal.n_cal_resistant} R",
        f"- finite-sample guarantee available: **{conformal.guarantee_available}**",
    ]
    if result.coefficients:
        top = result.coefficients[:10]
        lines += [
            "",
            "## Top signed coefficients (statistical-association evidence)",
            *[f"- `{c.feature}`: {c.coefficient:+.3f}" for c in top],
        ]
    lines.append("")
    return "\n".join(lines)
