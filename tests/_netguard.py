"""Shared fixture for the in-process-ASGI / AppTest suites (api/, ui/).

The repo-wide autouse ``_no_network`` guard (tests/conftest.py) monkeypatches ``socket.socket``
to fail any unit test that reaches the network. FastAPI's ``TestClient`` and Streamlit's
``AppTest`` make **no** real outbound connection (in-memory ASGI transport / in-process script
runner), but they DO spin up an asyncio event loop whose self-pipe calls ``socket.socketpair()``.
On Linux that resolves to the native C ``socketpair`` and never touches the patched class; on
Windows it falls back to the pure-Python implementation that calls ``socket.socket(...)`` -- so
the guard turns event-loop creation into a hang (the portal thread dies, the caller waits
forever). Restoring the real socket for these deliberately-offline integration tests removes the
Windows-only hang while leaving the guard in force for every other suite.
"""

from __future__ import annotations

import socket as _socket_module

import pytest

#: Captured at conftest-import time, before any per-test patching -- the genuine socket class.
_REAL_SOCKET = _socket_module.socket


@pytest.fixture(autouse=True)
def permit_in_process_asgi(monkeypatch: pytest.MonkeyPatch) -> None:
    """Restore the real ``socket.socket`` so the event loop's socketpair works (these suites
    make no real network call; MockAnnotator + MockLLMClient + EvidenceRAG.from_seed only)."""
    monkeypatch.setattr(_socket_module, "socket", _REAL_SOCKET)
