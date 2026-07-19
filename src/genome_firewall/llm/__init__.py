"""Provider-agnostic LLM abstraction (OpenAI primary, MockLLMClient for tests).

Used ONLY for evidence RAG, grounded report narration, and review. Never a source of
a verdict or confidence. Importable only from ``report``/``kb`` — never from the
prediction path (``reader``/``features``/``predictor``).
"""

from __future__ import annotations

from genome_firewall.llm.client import LLMClient, parse_structured_response
from genome_firewall.llm.errors import (
    LLMBackendError,
    LLMConfigError,
    LLMError,
    LLMParseError,
    LLMRefusalError,
)
from genome_firewall.llm.factory import make_client
from genome_firewall.llm.mock import MockLLMClient
from genome_firewall.llm.openai_backend import OpenAIBackend
from genome_firewall.llm.settings import LLMSettings
from genome_firewall.llm.types import LLMResponse, Message, Role

__all__ = [
    "LLMBackendError",
    "LLMClient",
    "LLMConfigError",
    "LLMError",
    "LLMParseError",
    "LLMRefusalError",
    "LLMResponse",
    "LLMSettings",
    "Message",
    "MockLLMClient",
    "OpenAIBackend",
    "Role",
    "make_client",
    "parse_structured_response",
]
