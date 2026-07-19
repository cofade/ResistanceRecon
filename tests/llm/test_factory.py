"""Unit tests for the client factory: key -> OpenAIBackend, no key -> None (deterministic)."""

from __future__ import annotations

from genome_firewall.llm.factory import make_client
from genome_firewall.llm.openai_backend import OpenAIBackend
from genome_firewall.llm.settings import LLMSettings


def test_no_key_yields_no_client() -> None:
    assert make_client(LLMSettings(openai_api_key=None)) is None


def test_key_yields_openai_backend_but_does_not_call_it() -> None:
    client = make_client(LLMSettings(openai_api_key="sk-test", openai_model="gpt-x"))
    assert isinstance(client, OpenAIBackend)
    # No provider client is constructed until a call is made.
    assert client._client is None
