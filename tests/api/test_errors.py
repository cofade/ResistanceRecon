"""Unit coverage for the API error handlers (issue #27): the {ok:false,error} envelope shapes
and HTTP status per error class, and the backstop that a genuinely unexpected exception is
answered with a generic message (never a raw traceback echoed to the client).

The handlers are plain sync functions, so each test calls one directly -- no event loop, no
pytest-asyncio.
"""

from __future__ import annotations

from fastapi import Request

from genome_firewall.api import errors
from genome_firewall.reader.fasta_parser import FastaParseError
from genome_firewall.service import PipelineError


def _request() -> Request:
    return Request({"type": "http", "method": "POST", "headers": [], "path": "/predict"})


def test_client_error_is_422_with_message() -> None:
    response = errors.handle_client_error(_request(), FastaParseError("bad fasta"))
    assert response.status_code == 422
    assert response.body == b'{"ok":false,"error":"bad fasta"}'


def test_pipeline_error_is_503_with_message() -> None:
    response = errors.handle_pipeline_error(_request(), PipelineError("annotation failed"))
    assert response.status_code == 503
    assert b'"ok":false' in response.body
    assert b"annotation failed" in response.body


def test_unexpected_error_is_503_generic_without_leak() -> None:
    secret = "sensitive internal detail /abs/path/x.py line 42"
    response = errors.handle_unexpected_error(_request(), RuntimeError(secret))
    assert response.status_code == 503
    assert b'"ok":false' in response.body
    assert secret.encode() not in response.body  # the raw exception text is never echoed
