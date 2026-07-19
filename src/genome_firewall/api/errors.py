"""Structured ``{ok:false, error}`` envelopes for every pipeline/tool failure (issue #27,
ADR-0007) -- registered as FastAPI exception handlers in api/main.py.

Never a traceback: a genuinely unexpected exception is logged server-side and answered with a
generic, non-sensitive message; only the already-safe, crafted messages of FastaParseError /
PipelineError (both sourced from reader/predictor/annotation, none of which ever embeds a
filesystem path outside the upload's own temp dir or a stack frame) are echoed to the client.
"""

from __future__ import annotations

import logging

from fastapi import Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

# Sync handlers (Starlette supports both sync and async exception handlers): trivial, no I/O,
# and directly unit-testable without spinning up an event loop -- which on Windows would create
# a socketpair the test suite's no-network guard blocks.


def handle_client_error(request: Request, exc: Exception) -> JSONResponse:
    """A malformed request the caller can fix (e.g. FastaParseError, an invalid genome_id)."""
    del request
    return JSONResponse(status_code=422, content={"ok": False, "error": str(exc)})


def handle_pipeline_error(request: Request, exc: Exception) -> JSONResponse:
    """A tool/infra failure inside the pipeline (annotation ok=False, predictor compat error)."""
    del request
    logger.warning("pipeline error: %s", exc)
    return JSONResponse(status_code=503, content={"ok": False, "error": str(exc)})


def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    """Anything not already a typed client/pipeline error -- logged in full server-side, but
    the client only ever sees a generic message. This is the backstop that keeps golden rule
    #4-adjacent honesty (never silently swallow) without leaking internals (never a traceback).
    """
    del request
    logger.error("unexpected error in request handling", exc_info=exc)
    return JSONResponse(
        status_code=503,
        content={"ok": False, "error": "internal pipeline error; see server logs"},
    )
