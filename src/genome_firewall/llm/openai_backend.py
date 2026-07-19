"""OpenAI backend (structured outputs). Thin by design: it builds a strict json-schema
request, delegates parsing to the shared ``parse_structured_response``, and maps failures to
typed ``LLMError``s. The real ``OpenAI(...)`` client is constructed lazily and only when a key
is present, so importing this module -- or constructing the backend -- never touches the
network; CI never instantiates the real client (it is exercised via an injected transport).
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from genome_firewall.llm.client import parse_structured_response
from genome_firewall.llm.errors import LLMBackendError, LLMRefusalError
from genome_firewall.llm.types import LLMResponse, Message, T

#: A factory that builds the underlying provider client from an API key. Overridable in tests
#: with a fake transport so the request/response mapping is covered without a key or network.
ClientFactory = Callable[[str], Any]

DEFAULT_OPENAI_MODEL = "gpt-4o-2024-08-06"


def _default_client_factory(api_key: str) -> Any:
    from openai import OpenAI  # lazy: importing this module must not require the SDK/network

    return OpenAI(api_key=api_key)  # pragma: no cover - real network client, never built in CI


class OpenAIBackend:
    """Provider-agnostic ``LLMClient`` implementation backed by OpenAI structured outputs."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str = DEFAULT_OPENAI_MODEL,
        client_factory: ClientFactory | None = None,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._client_factory = client_factory or _default_client_factory
        self._client: Any | None = None

    def _client_or_build(self) -> Any:
        if self._client is None:
            self._client = self._client_factory(self._api_key)
        return self._client

    def _schema_format(self, schema: type[T], tool_name: str) -> dict[str, Any]:
        # strict=False deliberately: OpenAI strict mode requires every property to be `required`
        # (no defaults), but the narrator/reviewer schemas have optional fields with defaults
        # (citations/caveats/per_claim/evidence_ref). Groundedness does not depend on strict mode
        # anyway -- parse_structured_response re-validates the response and fails closed.
        return {
            "type": "json_schema",
            "json_schema": {
                "name": tool_name,
                "schema": schema.model_json_schema(),
                "strict": False,
            },
        }

    def complete_structured(
        self, messages: Sequence[Message], *, schema: type[T], tool_name: str
    ) -> LLMResponse[T]:
        client = self._client_or_build()
        payload = [{"role": m.role, "content": m.content} for m in messages]
        try:
            response = client.chat.completions.create(
                model=self._model,
                messages=payload,
                response_format=self._schema_format(schema, tool_name),
                temperature=0,
            )
        except Exception as exc:
            # Normalize any SDK/transport failure (network, quota, 5xx) into a typed error.
            raise LLMBackendError(f"OpenAI call failed: {exc}") from exc

        choice = response.choices[0]
        content = choice.message.content or ""
        if not content:
            raise LLMRefusalError(
                f"OpenAI returned empty content (finish_reason={choice.finish_reason!r})"
            )
        parsed = parse_structured_response(content, schema)
        return LLMResponse(
            parsed=parsed,
            raw_text=content,
            model=self._model,
            finish_reason=str(choice.finish_reason),
        )
