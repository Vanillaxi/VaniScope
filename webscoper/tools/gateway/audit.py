from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel


class ToolAuditEvent(BaseModel):
    timestamp: str
    task_id: str
    workflow_backend: str
    tool_name: str
    provider_type: str | None = None
    permission: str | None = None
    risk_level: str | None = None
    decision: str
    status: str
    error_type: str | None = None
    error_message: str | None = None
    duration_ms: float | None = None
    approval_id: str | None = None
    metadata: dict[str, Any] = {}


class ToolGatewayAuditStore:
    def __init__(self, output_path: Path | None = None) -> None:
        self.output_path = output_path
        self.events: list[ToolAuditEvent] = []

    def append(self, event: ToolAuditEvent) -> None:
        self.events.append(event)
        if self.output_path is None:
            return
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        with self.output_path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(event.model_dump(mode="json"), ensure_ascii=False))
            file.write("\n")


def utc_now() -> str:
    return datetime.now(UTC).isoformat()
