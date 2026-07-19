"""Unit tests for MockLLMClient -- the key-free, network-free CI stand-in."""

from __future__ import annotations

import pytest

from genome_firewall.llm.errors import LLMParseError, LLMRefusalError
from genome_firewall.llm.mock import MockLLMClient
from genome_firewall.llm.types import Message
from tests.llm.conftest import _Echo

_MESSAGES = [Message(role="user", content="go")]


def test_scripted_model_response_is_returned_and_reparsed() -> None:
    client = MockLLMClient({"echo": _Echo(text="hello", score=0.9)})
    response = client.complete_structured(_MESSAGES, schema=_Echo, tool_name="echo")
    assert response.parsed.text == "hello"
    assert response.model == "mock"


def test_scripted_raw_json_str_drives_the_shared_parser() -> None:
    client = MockLLMClient({"echo": '{"text": "raw", "score": 0.1}'})
    assert (
        client.complete_structured(_MESSAGES, schema=_Echo, tool_name="echo").parsed.text == "raw"
    )


def test_unscripted_tool_fails_closed() -> None:
    client = MockLLMClient({})
    with pytest.raises(LLMRefusalError):
        client.complete_structured(_MESSAGES, schema=_Echo, tool_name="missing")


def test_malformed_scripted_json_raises_parse_error() -> None:
    client = MockLLMClient({"echo": '{"text": "missing score"}'})
    with pytest.raises(LLMParseError):
        client.complete_structured(_MESSAGES, schema=_Echo, tool_name="echo")


def test_mock_needs_no_network() -> None:
    # The autouse _no_network guard (tests/conftest.py) is active in every unit test; a mock
    # call must complete without touching the socket.
    client = MockLLMClient({"echo": _Echo(text="x", score=0.0)})
    assert client.complete_structured(_MESSAGES, schema=_Echo, tool_name="echo").parsed.score == 0.0
