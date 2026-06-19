from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from webscoper.schemas.runtime import ApprovalRequest, TaskResumeResult
from webscoper.schemas.workflow import LangGraphResumeResult, WorkflowBackend


PlannerMode = Literal["deterministic", "fake_llm", "real_llm"]
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


class TaskCreateRequest(BaseModel):
    url: str
    click: str | None = None
    expect: str | None = None
    planner: PlannerMode = "deterministic"
    workflow: WorkflowBackend = "langgraph"
    reviewer: ReviewerMode = "deterministic"
    workspace: str | None = None
    reminder: str | None = None
    repair_attempts: int = 0
    revise_attempts: int = 0
    llm_config: str | None = None
    llm_provider: str | None = None
    model: str | None = None


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
    error: str | None = None


class TaskStatusResponse(BaseModel):
    task_id: str
    status: TaskStatus
    run_dir: str | None = None
    artifacts: list[str] = Field(default_factory=list)
    error: str | None = None


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
