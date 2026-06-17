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
    "task_paused",
    "task_resumed",
    "task_rejected",
    "resume_failed",
    "recovery_started",
    "recovery_attempt_started",
    "recovery_attempt_finished",
    "recovery_succeeded",
    "recovery_failed",
    "recovery_blocked",
    "llm_review_started",
    "llm_review_finished",
    "revision_plan_created",
    "report_revised",
    "final_review_finished",
    "revise_loop_finished",
    "workflow_started",
    "workflow_node_started",
    "workflow_node_finished",
    "workflow_finished",
    "workflow_failed",
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
