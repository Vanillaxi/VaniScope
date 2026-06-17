from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ToolCall(BaseModel):
    call_id: str
    tool_id: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    reason: str | None = None


class ToolResult(BaseModel):
    call_id: str
    tool_id: str
    status: str
    output: dict[str, Any] = Field(default_factory=dict)
    error_type: str | None = None
    error_message: str | None = None
    started_at: str | None = None
    ended_at: str | None = None


class ToolExecutionRecord(BaseModel):
    call: ToolCall
    result: ToolResult
