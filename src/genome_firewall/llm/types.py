"""Provider-agnostic message + response types for the LLM abstraction."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict

Role = Literal["system", "user", "assistant"]

#: The structured-output model an LLM call is forced to produce.
T = TypeVar("T", bound=BaseModel)


class Message(BaseModel):
    """One chat message. Verdicts/confidence only ever appear here as read-only context
    strings the model may reference -- never as a field the model can write (golden rule #1).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    role: Role
    content: str


@dataclass(frozen=True)
class LLMResponse(Generic[T]):
    """The validated structured output of one LLM call, plus provenance."""

    parsed: T
    raw_text: str
    model: str
    finish_reason: str
