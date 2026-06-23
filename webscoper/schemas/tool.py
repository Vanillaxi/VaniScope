from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


ToolExposure = Literal[
    "core",
    "contextual",
    "lazy",
    "hidden",
    "disabled",
    "compatibility",
]
WebExposure = Literal["allowed", "hidden", "approval_required"]
FixtureExposure = Literal["allowed", "hidden"]


class ToolSpec(BaseModel):
    tool_id: str
    name: str
    display_name: str | None = None
    description: str
    prompt: str
    tool_type: str = "local"
    loading_mode: str = "core"
    provider: str = "local"
    permission: str = "read_only"
    risk_level: str = "read_only"
    timeout_ms: int = 5000
    input_schema: dict[str, Any] = Field(default_factory=dict)
    output_schema: dict[str, Any] = Field(default_factory=dict)
    schema_summary: dict[str, str] = Field(default_factory=dict)
    required_context: list[str] = Field(default_factory=list)
    supported_modes: list[str] = Field(default_factory=lambda: ["guided", "auto_explore"])
    requires_session: bool = False
    produces_evidence: bool = False
    produces_screenshot: bool = False
    can_mutate_page: bool = False
    can_submit_external: bool = False
    public_web_allowed: bool = True
    local_fixture_allowed: bool = True
    enabled: bool = True
    reason_if_disabled: str | None = None
    compatibility_wrapper: bool = False
    exposure: ToolExposure = "core"
    public_web_exposure: WebExposure = "allowed"
    local_fixture_exposure: FixtureExposure = "allowed"
    real_llm_prompt_allowed: bool = True
    tags: list[str] = Field(default_factory=list)


class ToolDiscoveryResult(BaseModel):
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
