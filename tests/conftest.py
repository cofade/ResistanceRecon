"""Shared pytest fixtures.

Deliberately keeps the whole suite independent of AMRFinderPlus / Docker / WSL2 so
it runs in CI (see Documentation/research-findings/se-scaffolding.md). Heavy bio
tooling is exercised only through MockAnnotator against committed fixture TSVs.
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fail fast if a unit test accidentally reaches the network."""
    import socket

    def _guard(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("network access is disabled in unit tests; use a mock/fixture")

    monkeypatch.setattr(socket, "socket", _guard)
