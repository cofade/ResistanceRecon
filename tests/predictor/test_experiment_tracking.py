"""MLflow tracker port tests (ADR-0014): NullTracker inert, to_mlflow_uri Windows-path
handling, and crash-safety (a broken mlflow degrades a run to untracked, never raises)."""

from __future__ import annotations

import types

import pytest

from genome_firewall.predictor.experiment_tracking import (
    MLflowTracker,
    NullTracker,
    default_tracking_uri,
    mlflow_available,
    to_mlflow_uri,
)


def test_null_tracker_is_inert() -> None:
    tracker = NullTracker()
    assert tracker.start({"drug": "meropenem"}) is False
    assert tracker.active is False
    # None of these raise or do anything observable.
    tracker.log_params({"a": 1})
    tracker.log_metrics({"resistant_recall": 0.9})
    tracker.log_artifact("nonexistent.json")
    tracker.end()


def test_to_mlflow_uri_converts_windows_paths_but_passes_real_uris() -> None:
    assert to_mlflow_uri("C:/tmp/mlruns").startswith("file://")
    assert to_mlflow_uri("http://localhost:5000") == "http://localhost:5000"
    assert to_mlflow_uri("sqlite:///runs.db") == "sqlite:///runs.db"
    assert to_mlflow_uri("file:///already/a/uri") == "file:///already/a/uri"


def test_default_tracking_uri_is_mlruns_under_base(tmp_path: object) -> None:
    from pathlib import Path

    assert default_tracking_uri(Path(str(tmp_path))).endswith("mlruns")


def test_tracker_is_crash_safe_when_mlflow_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    # A broken/raising mlflow must degrade this run to untracked, never abort the caller.
    broken = types.ModuleType("mlflow")

    def _boom(*args: object, **kwargs: object) -> None:
        raise RuntimeError("simulated broken mlflow")

    broken.set_tracking_uri = _boom  # type: ignore[attr-defined]
    monkeypatch.setitem(__import__("sys").modules, "mlflow", broken)

    messages: list[str] = []
    tracker = MLflowTracker("C:/tmp/mlruns", log=messages.append)
    assert tracker.start({"drug": "gentamicin"}) is False
    assert tracker.active is False
    # Post-failure calls stay inert (guarded by _active) and never raise.
    tracker.log_metrics({"x": 1.0})
    tracker.end()
    assert any("untracked" in m for m in messages)


@pytest.mark.skipif(not mlflow_available(), reason="requires the optional 'tracking' extra")
def test_live_round_trip_logs_a_run(tmp_path: object) -> None:
    # Happy path against a local file store: start -> log params/metrics/artifact -> end.
    from pathlib import Path

    store = Path(str(tmp_path)) / "mlruns"
    artifact = Path(str(tmp_path)) / "metrics.json"
    artifact.write_text('{"resistant_recall": 0.9}', encoding="utf-8")

    tracker = MLflowTracker(store, experiment_name="gf-test", run_name="meropenem")
    assert tracker.start({"drug": "meropenem", "seed": 0, "skipped": None}) is True
    assert tracker.active is True
    assert tracker.run_id is not None
    tracker.log_params({"alpha": 0.1})
    tracker.log_metrics({"resistant_recall": 0.9, "brier": 0.12})
    tracker.log_artifact(artifact)
    tracker.end()
    assert tracker.active is False
    assert store.exists()  # the file store was created
