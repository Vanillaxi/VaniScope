from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


TaskEventKind = Literal[
    "task_created",
    "task_started",
    "prompt_built",
    "planner_started",
    "planner_finished",
    "tool_call_started",
    "tool_call_finished",
    "evidence_added",
    "report_written",
    "review_finished",
    "approval_required",
    "approval_decided",
    "risk_blocked",
    "task_finished",
    "task_failed",
]


class TaskEvent(BaseModel):
    event_id: str = ""
    task_id: str
    kind: TaskEventKind
    message: str
    created_at: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)


class TaskEventStreamRecord(BaseModel):
    event: TaskEventKind
    data: TaskEvent
