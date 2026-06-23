from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


ToolProviderType = Literal["local", "browser", "mcp", "remote"]
ToolPermission = Literal["read_only", "sensitive", "dangerous"]
ToolRiskLevel = Literal["read_only", "sensitive", "dangerous"]
ToolDecision = Literal["allowed", "approval_required", "blocked"]
ToolInvocationStatus = Literal["success", "failed", "blocked", "approval_required"]
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


class ToolSchema(BaseModel):
    schema: dict[str, Any] = Field(default_factory=dict)


class ToolDescriptor(BaseModel):
    tool_id: str
    name: str
    display_name: str | None = None
    description: str
    provider_type: ToolProviderType
    input_schema: ToolSchema = Field(default_factory=ToolSchema)
    output_schema: ToolSchema = Field(default_factory=ToolSchema)
    loading_mode: Literal["core", "contextual", "lazy", "disabled"] = "core"
    provider: str = "local"
    permission: ToolPermission = "read_only"
    risk_level: ToolRiskLevel = "read_only"
    required_context: list[str] = Field(default_factory=list)
    schema_summary: dict[str, str] = Field(default_factory=dict)
    supported_modes: list[str] = Field(default_factory=list)
    requires_session: bool = False
    produces_evidence: bool = False
    produces_screenshot: bool = False
    can_mutate_page: bool = False
    can_submit_external: bool = False
    public_web_allowed: bool = True
    local_fixture_allowed: bool = True
    compatibility_wrapper: bool = False
    timeout_seconds: float = 10.0
    enabled: bool = True
    exposure: ToolExposure = "core"
    public_web_exposure: WebExposure = "allowed"
    local_fixture_exposure: FixtureExposure = "allowed"
    real_llm_prompt_allowed: bool = True
    version: str = "1"
    tags: list[str] = Field(default_factory=list)
    reason_if_disabled: str | None = None


class ToolInvocationRequest(BaseModel):
    task_id: str
    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    call_id: str | None = None
    workflow_backend: str = "langgraph"
    run_dir: str | None = None
    context_snapshot: dict[str, Any] | None = None
    page_observation: dict[str, Any] | None = None
    approval_override_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ToolInvocationResult(BaseModel):
    task_id: str
    tool_name: str
    call_id: str | None = None
    provider_type: ToolProviderType | None = None
    decision: ToolDecision
    status: ToolInvocationStatus
    output: dict[str, Any] = Field(default_factory=dict)
    error_type: str | None = None
    error_message: str | None = None
    approval_id: str | None = None
    started_at: str | None = None
    ended_at: str | None = None
    duration_ms: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
