"""LLM configuration, read from the environment / a local .env (never committed).

When ``OPENAI_API_KEY`` is absent -- as in CI -- the factory yields no client and the
report pipeline serves the deterministic template (``review_status='llm_disabled'``).
"""

from __future__ import annotations

from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

#: Reasoning effort accepted by OpenAI reasoning models (the API's supported values, verified
#: live against gpt-5.6-luna). "xhigh" is the "Extra High" tier. Must match ``openai_model``.
ReasoningEffort = Literal["none", "low", "medium", "high", "xhigh"]


class LLMSettings(BaseSettings):
    """Provider settings. ``openai_api_key`` maps to the ``OPENAI_API_KEY`` env var."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    openai_api_key: str | None = None
    #: Default model is the GPT-5.6 Luna reasoning model (maps to OPENAI_MODEL).
    openai_model: str = "gpt-5.6-luna"
    #: "Extra High" reasoning by default (maps to OPENAI_REASONING_EFFORT).
    openai_reasoning_effort: ReasoningEffort = "xhigh"
