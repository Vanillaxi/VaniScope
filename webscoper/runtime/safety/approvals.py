from __future__ import annotations

import json
import threading
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from webscoper.schemas.runtime import (
    ApprovalDecision,
    ApprovalRequest,
    RiskCheckResult,
    PendingToolCall,
)


class ApprovalStoreError(ValueError):
    pass


class ApprovalStore:
    def __init__(self, output_path: Path | None = None) -> None:
        self.output_path = output_path
        self._requests: dict[str, ApprovalRequest] = {}
        self._task_index: dict[str, list[str]] = defaultdict(list)
        self._risk_checks: dict[str, list[RiskCheckResult]] = defaultdict(list)
        self._next_id = 1
        self._lock = threading.Lock()

    def create_request(
        self,
        task_id: str,
        reason: str,
        risk_level: str,
        tool_name: str | None = None,
        action_type: str | None = None,
        target_hint: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ApprovalRequest:
        with self._lock:
            approval = ApprovalRequest(
                approval_id=f"appr_{self._next_id:06d}",
                task_id=task_id,
                status="pending",
                reason=reason,
                risk_level=risk_level,
                tool_name=tool_name,
                action_type=action_type,
                target_hint=target_hint,
                created_at=_utc_now(),
                metadata=_json_safe(metadata or {}),
            )
            self._next_id += 1
            self._requests[approval.approval_id] = approval
            self._task_index[task_id].append(approval.approval_id)
        self.write_jsonl()
        return approval

    def decide(
        self,
        approval_id: str,
        approved: bool,
        decided_by: str = "local_user",
        reason: str | None = None,
    ) -> ApprovalRequest:
        with self._lock:
            request = self._requests.get(approval_id)
            if request is None:
                raise ApprovalStoreError(f"Approval request not found: {approval_id}")
            if request.status != "pending":
                raise ApprovalStoreError(
                    f"Approval request already decided: {approval_id}"
                )

            now = _utc_now()
            updated = request.model_copy(
                update={
                    "status": "approved" if approved else "rejected",
                    "decided_at": now,
                    "decision": ApprovalDecision(
                        approved=approved,
                        decided_by=decided_by,
                        reason=reason,
                        created_at=now,
                    ),
                }
            )
            self._requests[approval_id] = updated
        self.write_jsonl()
        return updated

    def get(self, approval_id: str) -> ApprovalRequest | None:
        with self._lock:
            return self._requests.get(approval_id)

    def list_for_task(self, task_id: str) -> list[ApprovalRequest]:
        with self._lock:
            return [
                self._requests[approval_id]
                for approval_id in self._task_index.get(task_id, [])
                if approval_id in self._requests
            ]

    def record_check(self, task_id: str, result: RiskCheckResult) -> None:
        with self._lock:
            self._risk_checks[task_id].append(result)

    def write_jsonl(self) -> None:
        if self.output_path is None:
            return
        self.write_jsonl_for_task(None, self.output_path)

    def write_jsonl_for_task(self, task_id: str | None, output_path: Path) -> None:
        approvals = self._list_all() if task_id is None else self.list_for_task(task_id)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("w", encoding="utf-8") as file:
            for approval in approvals:
                file.write(
                    json.dumps(approval.model_dump(mode="json"), ensure_ascii=False)
                )
                file.write("\n")

    def write_risk_report(self, task_id: str, output_path: Path) -> None:
        with self._lock:
            checks = list(self._risk_checks.get(task_id, []))
        approvals = self.list_for_task(task_id)
        signals = [
            signal.model_dump(mode="json")
            for check in checks
            for signal in check.signals
        ]
        report = {
            "task_id": task_id,
            "total_risk_signals": len(signals),
            "approval_required": sum(1 for check in checks if check.requires_approval),
            "blocked": sum(1 for check in checks if check.blocked),
            "signals": signals,
            "approval_ids": [approval.approval_id for approval in approvals],
        }
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(report, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def _list_all(self) -> list[ApprovalRequest]:
        with self._lock:
            return list(self._requests.values())


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
                file.write(
                    json.dumps(pending.model_dump(mode="json"), ensure_ascii=False)
                )
                file.write("\n")


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _json_safe(payload: dict[str, Any]) -> dict[str, Any]:
    return json.loads(json.dumps(payload, ensure_ascii=False, default=str))
