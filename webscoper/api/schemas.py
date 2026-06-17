from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


PlannerMode = Literal["deterministic", "fake_llm", "real_llm"]
TaskStatus = Literal["running", "succeeded", "failed", "not_found"]


class TaskCreateRequest(BaseModel):
    url: str
    click: str | None = None
    expect: str | None = None
    planner: PlannerMode = "deterministic"
    workspace: str | None = None
    reminder: str | None = None
    repair_attempts: int = 0
    llm_config: str | None = None
    llm_provider: str | None = None
    model: str | None = None


class TaskCreateResponse(BaseModel):
    task_id: str
    status: Literal["running", "succeeded", "failed"]
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
