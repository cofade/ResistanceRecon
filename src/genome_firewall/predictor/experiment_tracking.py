"""MLflow experiment tracking for the training run (ADR-0014).

Ported and slimmed from the proven ``digitalsreeni-image-annotator`` tracker (see
Documentation/reuse-inventory.md): the ``MLflowTracker`` / :class:`NullTracker` split, the
lazy-``import mlflow``-inside-methods idiom, the blanket crash-safety (a tracking error
degrades that one run to *untracked* but never aborts training), and ``to_mlflow_uri`` (a
bare Windows drive path is read by MLflow as URI scheme ``c`` and rejected, silently
degrading local-file tracking to untracked -- so local paths are converted to ``file://``).
The Qt/GUI parts (signals, deep-link URLs, the browser-launching UI server) are dropped.

Tracking is strictly OFF the inference/verdict path -- it observes training only, and even
its total absence changes no model output (that is what :class:`NullTracker` proves). Never
imports genome_firewall.llm. mlflow is the optional ``tracking`` extra; every use is lazy and
guarded, so the package imports and trains fine without it installed.
"""

from __future__ import annotations

import contextlib
import os
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

_DEFAULT_EXPERIMENT = "genome-firewall-predictor"
_MLRUNS_DIRNAME = "mlruns"

# Cache the import probe -- mlflow's import is non-trivial and the answer never changes
# within a process.
_AVAILABLE: bool | None = None


def to_mlflow_uri(path_or_uri: str | Path) -> str:
    """Return a value MLflow accepts as a tracking URI.

    MLflow validates the URI *scheme*, so a bare Windows path such as ``C:\\Users\\me\\mlruns``
    is read as scheme ``c`` and rejected -- local-file tracking then silently degrades to
    untracked on Windows. Local filesystem paths are therefore expressed as ``file://`` URIs;
    genuine URIs (``file``, ``http(s)``, ``sqlite``, ``databricks`` ...) pass through unchanged.
    """
    text = str(path_or_uri)
    scheme = urlparse(text).scheme
    # Empty scheme = POSIX/relative path; a single-letter scheme is a Windows drive (``C:``),
    # not a real URI scheme -- both are local filesystem paths.
    if len(scheme) > 1:
        return text
    return Path(text).resolve().as_uri()


def mlflow_available() -> bool:
    """True if ``mlflow`` (the optional ``tracking`` extra) can be imported."""
    global _AVAILABLE
    if _AVAILABLE is None:
        try:
            import mlflow  # noqa: F401

            _AVAILABLE = True
        except Exception:  # pragma: no cover - environment-dependent
            _AVAILABLE = False
    return _AVAILABLE


def default_tracking_uri(project_dir: Path | None = None) -> str:
    """The default local file store: ``<project_dir-or-cwd>/mlruns`` (gitignored)."""
    base = project_dir if project_dir is not None else Path.cwd()
    return str(base / _MLRUNS_DIRNAME)


class MLflowTracker:
    """A crash-safe MLflow run wrapper for one training run.

    Any error raised by MLflow -- including a broken/absent install -- is caught and reported
    via the ``log`` callback but never propagated: a tracking failure degrades this run to
    untracked rather than aborting training. When a trainer is called without a tracker
    (programmatic/tests) a :class:`NullTracker` no-op stands in.
    """

    def __init__(
        self,
        tracking_uri: str | Path,
        experiment_name: str = _DEFAULT_EXPERIMENT,
        run_name: str | None = None,
        log: Callable[[str], None] | None = None,
    ) -> None:
        self._uri = tracking_uri
        self._experiment = experiment_name or _DEFAULT_EXPERIMENT
        self._run_name = run_name
        self._log = log
        self._active = False  # True only between a successful start() and end()
        self.run_id: str | None = None
        self.experiment_id: str | None = None

    def _emit(self, message: str) -> None:
        if self._log is not None:
            # A logging sink must never break tracking.
            with contextlib.suppress(Exception):  # pragma: no cover
                self._log(message)

    @property
    def active(self) -> bool:
        return self._active

    def start(self, params: Mapping[str, Any] | None = None) -> bool:
        """Open the run and log ``params``. Returns True if tracking is live. The broad except
        is pure crash-safety -- a broken install or transient backend error degrades this one
        run to untracked rather than killing the training job."""
        try:
            import mlflow

            # mlflow 3.x puts the local file store into maintenance mode and raises on it
            # unless this opt-out is set -- which would silently degrade our documented
            # file-store default to untracked. setdefault so an explicit choice is kept.
            os.environ.setdefault("MLFLOW_ALLOW_FILE_STORE", "true")
            mlflow.set_tracking_uri(to_mlflow_uri(self._uri))
            mlflow.set_experiment(self._experiment)
            # Self-heal: a run stranded active (killed before end()) would make start_run raise
            # "Run already active" and silently degrade this run to untracked. Close it first.
            if mlflow.active_run() is not None:
                mlflow.end_run()
            run = mlflow.start_run(run_name=self._run_name)
            if params:
                mlflow.log_params({k: v for k, v in params.items() if v is not None})
            self._active = True
            self.run_id = run.info.run_id
            self.experiment_id = run.info.experiment_id
            self._emit(f"MLflow tracking -> {self._uri} (experiment {self._experiment!r}).")
        except Exception as exc:  # never let tracking abort training
            self._active = False
            self._emit(f"MLflow tracking unavailable ({exc}); continuing untracked.")
        return self._active

    def log_params(self, params: Mapping[str, Any]) -> None:
        if not self._active:
            return
        try:
            import mlflow

            mlflow.log_params({k: v for k, v in params.items() if v is not None})
        except Exception as exc:  # pragma: no cover - crash-safety
            self._emit(f"MLflow param logging failed ({exc}).")

    def log_metrics(self, metrics: Mapping[str, float], step: int | None = None) -> None:
        if not self._active:
            return
        try:
            import mlflow

            for name, value in metrics.items():
                if value is not None:
                    mlflow.log_metric(name, float(value), step=step)
        except Exception as exc:  # pragma: no cover - crash-safety
            self._emit(f"MLflow metric logging failed ({exc}).")

    def log_artifact(self, path: str | Path) -> None:
        if not self._active or not path:
            return
        try:
            import mlflow

            if os.path.exists(path):
                mlflow.log_artifact(str(path))
        except Exception as exc:  # pragma: no cover - crash-safety
            self._emit(f"MLflow artifact logging failed ({exc}).")

    def end(self) -> None:
        if not self._active:
            return
        try:
            import mlflow

            mlflow.end_run()
        except Exception as exc:  # pragma: no cover - crash-safety
            self._emit(f"MLflow run finalization failed ({exc}).")
        finally:
            self._active = False


class NullTracker:
    """No-op stand-in used when training is invoked without a tracker (tests/programmatic).

    Matches :class:`MLflowTracker`'s surface so callers need no ``None`` checks, and proves
    tracking is off the model-output path: with tracking entirely absent, training produces
    byte-identical models.
    """

    active = False
    run_id: str | None = None
    experiment_id: str | None = None

    def start(self, _params: Mapping[str, Any] | None = None) -> bool:
        return False

    def log_params(self, _params: Mapping[str, Any]) -> None:
        pass

    def log_metrics(self, _metrics: Mapping[str, float], _step: int | None = None) -> None:
        pass

    def log_artifact(self, _path: str | Path) -> None:
        pass

    def end(self) -> None:
        pass


#: A trainer accepts either a live tracker or the no-op stand-in.
Tracker = MLflowTracker | NullTracker
