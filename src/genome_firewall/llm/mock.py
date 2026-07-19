"""MockLLMClient -- the deterministic, key-free, network-free LLM stand-in every CI test
uses (mirrors annotation/MockAnnotator). Scripted per tool name; routes responses through
the same ``parse_structured_response`` the real backend uses; fails closed on an unscripted
call so a test can never silently pass against a response nobody wrote.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from pydantic import BaseModel

from genome_firewall.llm.client import parse_structured_response
from genome_firewall.llm.errors import LLMRefusalError
from genome_firewall.llm.types import LLMResponse, Message, T


class MockLLMClient:
    """Return a scripted response for each ``tool_name``.

    A scripted value may be a ``BaseModel`` (serialized then re-parsed, exercising the shared
    parser) or a raw JSON ``str`` (parsed as-is -- lets a test drive the ``LLMParseError``
    path with deliberately malformed output).
    """

    def __init__(self, responses: Mapping[str, str | BaseModel]) -> None:
        self._responses: dict[str, str | BaseModel] = dict(responses)

    def complete_structured(
        self, messages: Sequence[Message], *, schema: type[T], tool_name: str
    ) -> LLMResponse[T]:
        del messages  # signature parity; the mock is scripted purely by tool_name
        if tool_name not in self._responses:
            raise LLMRefusalError(f"MockLLMClient has no scripted response for tool {tool_name!r}")
        raw = self._responses[tool_name]
        raw_text = raw if isinstance(raw, str) else raw.model_dump_json()
        parsed = parse_structured_response(raw_text, schema)
        return LLMResponse(parsed=parsed, raw_text=raw_text, model="mock", finish_reason="stop")
