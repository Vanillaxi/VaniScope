from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ToolSpec(BaseModel):
    tool_id: str
    name: str
    description: str
    prompt: str
    tool_type: str = "local"
    loading_mode: str = "core"
    permission: str = "read_only"
    risk_level: str = "read_only"
    timeout_ms: int = 5000
    schema_summary: dict[str, str] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)


class ToolSearchResult(BaseModel):
    query: str
    matches: list[ToolSpec] = Field(default_factory=list)


class ToolCatalogSnapshot(BaseModel):
    core_tools: list[ToolSpec] = Field(default_factory=list)
    lazy_tools: list[ToolSpec] = Field(default_factory=list)
    runtime_tools: list[ToolSpec] = Field(default_factory=list)


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


class PlannedStep(BaseModel):
    step_id: str
    tool_call: ToolCall
    reason: str
    expected_outcome: str | None = None


class ExecutionPlan(BaseModel):
    plan_id: str
    task_id: str
    steps: list[PlannedStep] = Field(default_factory=list)


class ExecutionLoopResult(BaseModel):
    task_id: str
    status: str
    records: list[ToolExecutionRecord] = Field(default_factory=list)
    final_output: dict = Field(default_factory=dict)
    error_type: str | None = None
    error_message: str | None = None


class PlanValidationIssue(BaseModel):
    issue_type: str
    message: str
    step_id: str | None = None
    tool_id: str | None = None


class PlanValidationResult(BaseModel):
    status: str
    issues: list[PlanValidationIssue] = Field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.status == "success"
