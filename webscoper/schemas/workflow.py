from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


WorkflowBackend = Literal["native", "langgraph"]


class WorkflowRunResult(BaseModel):
    task_id: str
    backend: WorkflowBackend
    status: str
    run_dir: str | None = None
    artifacts: list[str] = Field(default_factory=list)
    error: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
