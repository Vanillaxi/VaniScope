from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


WorkflowBackend = Literal["langgraph"]


class WorkflowRunResult(BaseModel):
    task_id: str
    backend: WorkflowBackend
    status: str
    run_dir: str | None = None
    artifacts: list[str] = Field(default_factory=list)
    error: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class LangGraphInterruptRecord(BaseModel):
    interrupt_id: str
    task_id: str
    approval_id: str
    thread_id: str
    node_name: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class LangGraphResumePayload(BaseModel):
    approval_id: str
    approved: bool
    decided_by: str
    reason: str | None = None
    edited_arguments: dict[str, Any] | None = None


class LangGraphResumeResult(BaseModel):
    task_id: str
    approval_id: str
    resumed: bool
    status: str
    message: str
    error: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
