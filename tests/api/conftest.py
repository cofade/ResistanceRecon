"""api/ suite fixtures. See tests/_netguard.py for why the in-process ASGI tests re-enable the
real socket (event-loop socketpair vs the repo no-network guard on Windows)."""

from __future__ import annotations

from tests._netguard import permit_in_process_asgi  # noqa: F401  (autouse fixture re-export)
