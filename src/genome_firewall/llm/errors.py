"""Typed errors for the LLM abstraction. Every failure is explicit so the narrative
pipeline can fail closed to the deterministic template rather than surfacing a traceback.
"""

from __future__ import annotations


class LLMError(Exception):
    """Base class for every LLM-layer failure."""


class LLMConfigError(LLMError):
    """The client is misconfigured (e.g. a real backend requested with no API key)."""


class LLMBackendError(LLMError):
    """The provider call itself failed (network, quota, 5xx, timeout)."""


class LLMParseError(LLMError):
    """The provider returned content that did not validate against the requested schema."""


class LLMRefusalError(LLMError):
    """The provider refused / returned empty content, or the mock has no scripted response."""
