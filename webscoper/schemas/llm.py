from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from webscoper.schemas.tool_call import ToolCall


class LLMMessage(BaseModel):
    role: str
    content: str


class LLMRequest(BaseModel):
    messages: list[LLMMessage] = Field(default_factory=list)
    model: str = "fake-llm"
    temperature: float = 0.0
    max_tokens: int = 2048
    metadata: dict[str, Any] = Field(default_factory=dict)


class LLMResponse(BaseModel):
    content: str
    model: str = "fake-llm"
    usage: dict[str, Any] = Field(default_factory=dict)
    raw: dict[str, Any] = Field(default_factory=dict)


class ParsedToolCalls(BaseModel):
    status: str
    tool_calls: list[ToolCall] = Field(default_factory=list)
    error_type: str | None = None
    error_message: str | None = None
    raw_text: str | None = None
