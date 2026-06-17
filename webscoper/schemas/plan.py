from __future__ import annotations

from pydantic import BaseModel, Field

from webscoper.schemas.tool_call import ToolCall, ToolExecutionRecord


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
