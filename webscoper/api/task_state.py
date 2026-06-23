from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path


@dataclass
class TaskState:
    task_id: str
    status: str
    run_dir: Path
    workflow: str = "langgraph"
    thread_id: str | None = None
    artifacts: list[str] = field(default_factory=list)
    error: str | None = None
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    current_step: int | None = None
    current_phase: str | None = None


def status_from_context_state(state: str) -> str:
    if state == "completed":
        return "succeeded"
    if state in {
        "requires_approval",
        "waiting_for_approval",
        "resuming",
        "blocked",
        "rejected",
        "failed",
        "paused",
        "cancel_requested",
        "canceled",
        "stop_requested",
        "succeeded_partial",
    }:
        return state
    return "succeeded"


def status_from_transcript(run_dir: Path) -> tuple[str, str | None]:
    transcript_path = run_dir / "transcript.jsonl"
    if not transcript_path.exists():
        return "failed", "Missing transcript.jsonl"

    status = "failed"
    error: str | None = None
    for line in transcript_path.read_text(encoding="utf-8").splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        event_type = event.get("event_type")
        if event_type == "execution_completed":
            payload = event.get("payload")
            state_status = None
            if isinstance(payload, dict):
                state_payload = payload.get("state")
                if isinstance(state_payload, dict):
                    state_status = state_payload.get("status")
            status = "succeeded_partial" if state_status == "succeeded_partial" else "succeeded"
            error = None
        elif event_type == "execution_failed":
            status = "failed"
            payload = event.get("payload")
            if isinstance(payload, dict):
                state_payload = payload.get("state")
                if isinstance(state_payload, dict):
                    error = state_payload.get("error_message")
                    state_status = state_payload.get("status")
                    if state_status in {
                        "requires_approval",
                        "waiting_for_approval",
                        "blocked",
                        "rejected",
                        "paused",
                        "canceled",
                        "succeeded_partial",
                    }:
                        status = state_status
        elif event_type == "partial_report_generated":
            status = "succeeded_partial"
            error = None
        elif event_type == "task_canceled":
            status = "canceled"
            error = "Task canceled by user."
        elif event_type == "task_paused":
            status = "paused"
            error = None
    return status, error
