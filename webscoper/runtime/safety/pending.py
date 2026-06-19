from __future__ import annotations

import json
import threading
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from webscoper.schemas.runtime import PendingToolCall


class PendingApprovalManager:
    def __init__(self) -> None:
        self._pending_by_approval_id: dict[str, PendingToolCall] = {}
        self._task_index: dict[str, list[str]] = defaultdict(list)
        self._history: list[PendingToolCall] = []
        self._next_id = 1
        self._lock = threading.Lock()

    def create_pending_tool_call(
        self,
        task_id: str,
        approval_id: str,
        tool_name: str,
        arguments: dict[str, Any],
        tool_call_id: str | None = None,
        reason: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> PendingToolCall:
        with self._lock:
            if approval_id in self._pending_by_approval_id:
                raise ValueError(
                    f"Pending tool call already exists for approval: {approval_id}"
                )
            pending = PendingToolCall(
                pending_id=f"pending_{self._next_id:06d}",
                task_id=task_id,
                approval_id=approval_id,
                tool_call_id=tool_call_id,
                tool_name=tool_name,
                arguments=_json_safe(arguments),
                reason=reason or "Approval required before tool execution.",
                created_at=_utc_now(),
                metadata=_json_safe(metadata or {}),
            )
            self._next_id += 1
            self._pending_by_approval_id[approval_id] = pending
            self._task_index[task_id].append(approval_id)
            self._history.append(pending)
            return pending

    def get_by_approval_id(self, approval_id: str) -> PendingToolCall | None:
        with self._lock:
            return self._pending_by_approval_id.get(approval_id)

    def pop_by_approval_id(self, approval_id: str) -> PendingToolCall | None:
        with self._lock:
            return self._pending_by_approval_id.pop(approval_id, None)

    def list_for_task(self, task_id: str) -> list[PendingToolCall]:
        with self._lock:
            return [
                self._pending_by_approval_id[approval_id]
                for approval_id in self._task_index.get(task_id, [])
                if approval_id in self._pending_by_approval_id
            ]

    def write_jsonl(self, task_id: str, output_path: Path) -> None:
        with self._lock:
            pending_calls = [
                pending for pending in self._history if pending.task_id == task_id
            ]
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("w", encoding="utf-8") as file:
            for pending in pending_calls:
                file.write(json.dumps(pending.model_dump(mode="json"), ensure_ascii=False))
                file.write("\n")


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _json_safe(payload: dict[str, Any]) -> dict[str, Any]:
    return json.loads(json.dumps(payload, ensure_ascii=False, default=str))
