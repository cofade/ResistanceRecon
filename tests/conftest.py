"""Shared pytest fixtures.

Deliberately keeps the whole suite independent of AMRFinderPlus / Docker / WSL2 so
it runs in CI (see Documentation/research-findings/se-scaffolding.md). Heavy bio
tooling is exercised only through MockAnnotator against committed fixture TSVs.

Tests marked ``@pytest.mark.live`` hit real external services (BV-BRC FTPS/Solr) and
are the one deliberate exception to the no-network rule -- see tests/scripts/
test_fetch_bvbrc_live.py. They are skipped by default; opt in with GF_RUN_LIVE=1.
"""

from __future__ import annotations

import os

import pytest


@pytest.fixture(autouse=True)
def _no_network(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> None:
    """Fail fast if a unit test accidentally reaches the network.

    Bypassed for tests explicitly marked ``@pytest.mark.live`` -- those hit real
    external services on purpose and are skipped by default (see
    pytest_collection_modifyitems below), so opting into GF_RUN_LIVE=1 is the only
    way this guard is ever actually bypassed in a real run.
    """
    if request.node.get_closest_marker("live"):
        return
    import socket

    def _guard(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("network access is disabled in unit tests; use a mock/fixture")

    monkeypatch.setattr(socket, "socket", _guard)


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Skip ``@pytest.mark.live`` tests unless GF_RUN_LIVE=1 -- keeps CI green while
    still letting a developer opt into a real BV-BRC FTPS/Solr run locally."""
    if os.environ.get("GF_RUN_LIVE") == "1":
        return
    skip_live = pytest.mark.skip(reason="live network test; set GF_RUN_LIVE=1 to run")
    for item in items:
        if item.get_closest_marker("live"):
            item.add_marker(skip_live)
