"""LLM configuration, read from the environment / a local .env (never committed).

When ``OPENAI_API_KEY`` is absent -- as in CI -- the factory yields no client and the
report pipeline serves the deterministic template (``review_status='llm_disabled'``).
"""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class LLMSettings(BaseSettings):
    """Provider settings. ``openai_api_key`` maps to the ``OPENAI_API_KEY`` env var."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    openai_api_key: str | None = None
    openai_model: str = "gpt-4o-2024-08-06"
