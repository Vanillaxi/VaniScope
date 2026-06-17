from __future__ import annotations

from pydantic import BaseModel, Field

from webscoper.schemas.task import BudgetContext, SafetyContext, TaskSpec
from webscoper.schemas.version import VersionContext


class TraceContext(BaseModel):
    run_id: str
    run_dir: str
    trace_path: str | None = None
    transcript_path: str | None = None


class RuntimeState(BaseModel):
    status: str = "created"
    current_step: int = 0
    error_type: str | None = None
    error_message: str | None = None


class WebAgentContextSnapshot(BaseModel):
    task: TaskSpec
    trace: TraceContext
    version: VersionContext = Field(default_factory=VersionContext)
    budget: BudgetContext
    safety: SafetyContext
    state: RuntimeState = Field(default_factory=RuntimeState)
