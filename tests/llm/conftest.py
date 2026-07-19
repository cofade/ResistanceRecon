"""Tiny local structured-output schema for exercising the LLM client abstraction in
isolation (independent of report/nl_schemas)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class _Echo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str
    score: float
