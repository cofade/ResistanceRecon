"""The single swap point between the real and the (absent) LLM backend.

Returns ``None`` when no API key is configured -- the caller then serves the deterministic
path. Tests never use the factory; they inject a ``MockLLMClient`` directly.
"""

from __future__ import annotations

from genome_firewall.llm.client import LLMClient
from genome_firewall.llm.openai_backend import OpenAIBackend
from genome_firewall.llm.settings import LLMSettings


def make_client(settings: LLMSettings | None = None) -> LLMClient | None:
    """Build the configured LLM client, or ``None`` when no key is available."""
    settings = settings or LLMSettings()
    if settings.openai_api_key:
        return OpenAIBackend(
            api_key=settings.openai_api_key,
            model=settings.openai_model,
            reasoning_effort=settings.openai_reasoning_effort,
        )
    return None
