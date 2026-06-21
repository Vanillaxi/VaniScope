from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from webscoper.schemas.runtime import ApprovalRequest, TaskResumeResult
from webscoper.schemas.workflow import LangGraphResumeResult, WorkflowBackend
from webscoper.runtime.inspector.schemas import (
    RuntimeArtifactRef,
    RuntimeEvidenceLink,
    RuntimeExecutionGraphResponse,
    RuntimeInspectorResponse,
    RuntimeInspectorSummary,
    RuntimeTimelineItem,
    RuntimeTimelineResponse,
)


PlannerMode = Literal["deterministic", "fake", "fake_llm", "llm", "real_llm"]
ReviewerMode = Literal["deterministic", "fake_llm", "real_llm"]
TaskStatus = Literal[
    "running",
    "succeeded",
    "failed",
    "requires_approval",
    "resuming",
    "blocked",
    "rejected",
    "not_found",
]
TaskMode = Literal["auto_explore", "guided", "skill"]


class TaskCreateRequest(BaseModel):
    url: str
    conversation_id: str | None = None
    goal: str | None = None
    mode: TaskMode = "guided"
    click: str | None = None
    expect: str | None = None
    skill_id: str | None = None
    task_type: str | None = None
    query: str | None = None
    research_goal: str | None = None
    language: str = "auto"
    planner: PlannerMode = "deterministic"
    workflow: WorkflowBackend = "langgraph"
    reviewer: ReviewerMode = "deterministic"
    workspace: str | None = None
    reminder: str | None = None
    repair_attempts: int = 0
    revise_attempts: int = 0
    planner_mode: PlannerMode | None = None
    use_real_llm: bool = False
    llm_config: str | None = None
    llm_provider: str | None = None
    model: str | None = None
    dry_run: bool = False
    public_web_config: str | None = None
    max_steps: int | None = None


class TaskCreateResponse(BaseModel):
    task_id: str
    status: Literal[
        "running",
        "succeeded",
        "failed",
        "requires_approval",
        "resuming",
        "blocked",
        "rejected",
    ]
    run_dir: str
    artifacts: list[str] = Field(default_factory=list)
    skill_id: str | None = None
    task_type: str | None = None
    error: str | None = None


class TaskStatusResponse(BaseModel):
    task_id: str
    status: TaskStatus
    run_dir: str | None = None
    artifacts: list[str] = Field(default_factory=list)
    error: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    current_step: int | None = None
    current_phase: str | None = None
    skill_id: str | None = None
    task_type: str | None = None
    skill_status: str | None = None
    difficulty: str | None = None
    recommendation: str | None = None


class TaskArtifactListResponse(BaseModel):
    task_id: str
    artifacts: list[str] = Field(default_factory=list)


class TaskArtifactContentResponse(BaseModel):
    task_id: str
    artifact_name: str
    content: str


class ApprovalDecisionRequest(BaseModel):
    approved: bool
    decided_by: str = "local_user"
    reason: str | None = None


class ApprovalDecisionResponse(BaseModel):
    approval: ApprovalRequest
    resume_result: TaskResumeResult | LangGraphResumeResult | None = None


class DiagnosticsResponse(BaseModel):
    status: str
    service: str = "vaniscope-api"
    runtime_backend: Literal["langgraph"] = "langgraph"
    artifact_directory: dict[str, object] = Field(default_factory=dict)
    llm: dict[str, object] = Field(default_factory=dict)
    web: dict[str, object] = Field(default_factory=dict)
    registered_skills: list[dict[str, object]] = Field(default_factory=list)
    browser: dict[str, object] = Field(default_factory=dict)
    config: dict[str, object] = Field(default_factory=dict)


class ConversationCreateRequest(BaseModel):
    title: str | None = None
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class ConversationResponse(BaseModel):
    id: str
    title: str
    created_at: str
    updated_at: str
    last_task_id: str | None = None
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class MessageResponse(BaseModel):
    id: str
    conversation_id: str
    role: str
    content: str
    task_id: str | None = None
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    created_at: str


class ConversationDetailResponse(ConversationResponse):
    messages: list[MessageResponse] = Field(default_factory=list)
