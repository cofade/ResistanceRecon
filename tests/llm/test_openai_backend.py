"""Unit tests for OpenAIBackend via an injected fake transport -- covers the request/response
mapping with no API key and no network (the real OpenAI client is never constructed)."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from genome_firewall.llm.errors import LLMBackendError, LLMParseError, LLMRefusalError
from genome_firewall.llm.openai_backend import OpenAIBackend
from genome_firewall.llm.types import Message
from tests.llm.conftest import _Echo

_MESSAGES = [Message(role="system", content="sys"), Message(role="user", content="go")]


class _FakeCompletions:
    def __init__(self, *, content: str | None, finish_reason: str = "stop", raises: bool = False):
        self._content = content
        self._finish_reason = finish_reason
        self._raises = raises
        self.last_kwargs: dict[str, Any] | None = None

    def create(self, **kwargs: Any) -> Any:
        self.last_kwargs = kwargs
        if self._raises:
            raise RuntimeError("boom")
        message = SimpleNamespace(content=self._content)
        choice = SimpleNamespace(message=message, finish_reason=self._finish_reason)
        return SimpleNamespace(choices=[choice])


def _backend(fake: _FakeCompletions) -> OpenAIBackend:
    client = SimpleNamespace(chat=SimpleNamespace(completions=fake))
    return OpenAIBackend(api_key="sk-test", model="gpt-x", client_factory=lambda _key: client)


def test_happy_path_maps_request_and_parses_response() -> None:
    fake = _FakeCompletions(content='{"text": "hi", "score": 0.7}')
    backend = _backend(fake)
    response = backend.complete_structured(_MESSAGES, schema=_Echo, tool_name="echo_tool")

    assert response.parsed.text == "hi"
    assert response.model == "gpt-x"
    # Request mapping.
    kwargs = fake.last_kwargs
    assert kwargs is not None
    assert kwargs["model"] == "gpt-x"
    assert kwargs["temperature"] == 0
    assert kwargs["messages"] == [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "go"},
    ]
    assert kwargs["response_format"]["type"] == "json_schema"
    assert kwargs["response_format"]["json_schema"]["name"] == "echo_tool"


def test_empty_content_is_a_refusal() -> None:
    backend = _backend(_FakeCompletions(content="", finish_reason="content_filter"))
    with pytest.raises(LLMRefusalError):
        backend.complete_structured(_MESSAGES, schema=_Echo, tool_name="echo_tool")


def test_transport_exception_becomes_backend_error() -> None:
    backend = _backend(_FakeCompletions(content=None, raises=True))
    with pytest.raises(LLMBackendError):
        backend.complete_structured(_MESSAGES, schema=_Echo, tool_name="echo_tool")


def test_malformed_response_raises_parse_error() -> None:
    backend = _backend(_FakeCompletions(content='{"text": "no score"}'))
    with pytest.raises(LLMParseError):
        backend.complete_structured(_MESSAGES, schema=_Echo, tool_name="echo_tool")


def test_provider_client_is_built_lazily_once() -> None:
    fake = _FakeCompletions(content='{"text": "a", "score": 0.1}')
    built = 0

    def factory(_key: str) -> Any:
        nonlocal built
        built += 1
        return SimpleNamespace(chat=SimpleNamespace(completions=fake))

    backend = OpenAIBackend(api_key="sk", model="m", client_factory=factory)
    assert built == 0  # not built at construction
    backend.complete_structured(_MESSAGES, schema=_Echo, tool_name="t")
    backend.complete_structured(_MESSAGES, schema=_Echo, tool_name="t")
    assert built == 1  # built once, reused
