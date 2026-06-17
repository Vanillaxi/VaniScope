from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


class TraceStep(BaseModel):
    step_id: str
    run_id: str
    phase: str
    actor: str
    action_type: str
    status: str
    url_before: str | None = None
    url_after: str | None = None
    title: str | None = None
    observation: dict[str, Any] | None = None
    screenshot_path: str | None = None
    error_type: str | None = None
    error_message: str | None = None
    latency_ms: int | None = None
    created_at: str = Field(default_factory=utc_now_iso)
