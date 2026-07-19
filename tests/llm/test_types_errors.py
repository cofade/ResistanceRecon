"""Unit tests for the LLM types, error hierarchy, and shared parser."""

from __future__ import annotations

import pytest

from genome_firewall.llm.client import parse_structured_response
from genome_firewall.llm.errors import (
    LLMBackendError,
    LLMConfigError,
    LLMError,
    LLMParseError,
    LLMRefusalError,
)
from genome_firewall.llm.types import LLMResponse, Message
from tests.llm.conftest import _Echo


def test_message_is_frozen_and_forbids_extra_fields() -> None:
    msg = Message(role="user", content="hi")
    assert msg.role == "user"
    with pytest.raises(ValueError):
        Message(role="user", content="hi", extra="nope")  # type: ignore[call-arg]


def test_parse_structured_response_returns_typed_object() -> None:
    parsed = parse_structured_response('{"text": "ok", "score": 0.5}', _Echo)
    assert parsed.text == "ok"
    assert parsed.score == 0.5


def test_parse_structured_response_raises_on_malformed_output() -> None:
    with pytest.raises(LLMParseError):
        parse_structured_response('{"text": "ok"}', _Echo)  # missing score
    with pytest.raises(LLMParseError):
        parse_structured_response("not json at all", _Echo)


def test_error_hierarchy() -> None:
    for err in (LLMConfigError, LLMBackendError, LLMParseError, LLMRefusalError):
        assert issubclass(err, LLMError)


def test_llm_response_carries_provenance() -> None:
    response = LLMResponse(
        parsed=_Echo(text="x", score=1.0), raw_text="{}", model="m", finish_reason="stop"
    )
    assert response.model == "m"
    assert response.finish_reason == "stop"
