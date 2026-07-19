"""The provider-agnostic ``LLMClient`` Protocol and the single production response parser
reused by every backend (mock and real alike), so mock and live output are validated by the
exact same code path -- structurally identical by construction, not by discipline.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from pydantic import ValidationError

from genome_firewall.llm.errors import LLMParseError
from genome_firewall.llm.types import LLMResponse, Message, T


def parse_structured_response(raw_text: str, schema: type[T]) -> T:
    """Validate raw model output against the requested schema, raising ``LLMParseError``.

    The one place raw provider text becomes a typed object. Both ``MockLLMClient`` and
    ``OpenAIBackend`` route through here.
    """
    try:
        return schema.model_validate_json(raw_text)
    except ValidationError as exc:
        raise LLMParseError(
            f"LLM output did not validate against {schema.__name__}: {exc}"
        ) from exc


class LLMClient(Protocol):
    """A structured-output-only client: the model is always forced to produce ``schema``.

    Restricting the surface to structured output (no free-form completion) keeps the LLM
    boundary tight -- there is no call shape that could return an unconstrained verdict.
    """

    def complete_structured(
        self, messages: Sequence[Message], *, schema: type[T], tool_name: str
    ) -> LLMResponse[T]: ...
