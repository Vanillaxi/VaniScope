from __future__ import annotations

import json
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from webscoper.runtime.safety.approvals import ApprovalStore
from webscoper.runtime.execution.events import TaskEventSink
from webscoper.runtime.safety.pending import PendingApprovalManager
from webscoper.schemas.runtime import RiskCheckResult
from webscoper.schemas.workflow import (
    LangGraphInterruptRecord,
    LangGraphResumePayload,
)


class LangGraphApprovalBridge:
    def __init__(
        self,
        approval_store: ApprovalStore,
        pending_manager: PendingApprovalManager,
        event_sink: TaskEventSink | None = None,
    ) -> None:
        self.approval_store = approval_store
        self.pending_manager = pending_manager
        self.event_sink = event_sink
        self._next_interrupt_id = 1
        self._interrupts_by_task: dict[str, list[LangGraphInterruptRecord]] = (
            defaultdict(list)
        )

    def create_interrupt_payload(
        self,
        *,
        task_id: str,
        thread_id: str,
        tool_name: str,
        arguments: dict[str, Any],
        risk_result: Any,
        node_name: str | None = None,
        tool_call_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        risk = _coerce_risk_result(risk_result)
        pending = self._find_existing_pending(
            task_id=task_id,
            tool_name=tool_name,
            arguments=arguments,
        )
        approval = (
            self.approval_store.get(pending.approval_id)
            if pending is not None
            else None
        )

        if approval is None:
            action_type, target_hint = _action_details(arguments)
            approval = self.approval_store.create_request(
                task_id=task_id,
                reason=risk.reason,
                risk_level=risk.risk_level,
                tool_name=tool_name,
                action_type=action_type,
                target_hint=target_hint,
                metadata={
                    "workflow": "langgraph",
                    "thread_id": thread_id,
                    "risk_check": risk.model_dump(mode="json"),
                    **(metadata or {}),
                },
            )
            risk = risk.model_copy(
                update={"approval_request_id": approval.approval_id}
            )
            pending = self.pending_manager.create_pending_tool_call(
                task_id=task_id,
                approval_id=approval.approval_id,
                tool_name=tool_name,
                arguments=arguments,
                tool_call_id=tool_call_id,
                reason=risk.reason,
                metadata={
                    "workflow": "langgraph",
                    "thread_id": thread_id,
                    "risk_check": risk.model_dump(mode="json"),
                    **(metadata or {}),
                },
            )
            self.approval_store.record_check(task_id, risk)

        existing_record = pending.metadata.get("langgraph_interrupt")
        if isinstance(existing_record, dict):
            record = LangGraphInterruptRecord.model_validate(existing_record)
        else:
            interrupt_payload = {
                "approval_id": approval.approval_id,
                "task_id": task_id,
                "thread_id": thread_id,
                "tool_name": tool_name,
                "arguments": _json_safe(arguments),
                "risk_check": risk.model_dump(mode="json"),
                "pending_tool_call": pending.model_dump(mode="json"),
            }
            record = LangGraphInterruptRecord(
                interrupt_id=self._new_interrupt_id(),
                task_id=task_id,
                approval_id=approval.approval_id,
                thread_id=thread_id,
                node_name=node_name,
                payload=interrupt_payload,
                created_at=_utc_now(),
                metadata=_json_safe(metadata or {}),
            )
            pending.metadata["langgraph_interrupt"] = record.model_dump(mode="json")
            self._interrupts_by_task[task_id].append(record)

        payload = {
            "interrupt_id": record.interrupt_id,
            "approval_id": approval.approval_id,
            "task_id": task_id,
            "thread_id": thread_id,
            "node_name": node_name,
            "tool_name": tool_name,
            "arguments": _json_safe(arguments),
            "risk_check": risk.model_dump(mode="json"),
            "approval_request": approval.model_dump(mode="json"),
            "pending_tool_call": pending.model_dump(mode="json"),
            "metadata": _json_safe(metadata or {}),
        }
        payload = _json_safe(payload)

        if approval.status == "pending":
            self._emit(
                "approval_required",
                "Approval required before tool execution",
                payload,
            )
            self._emit(
                "langgraph_interrupted",
                "LangGraph workflow interrupted for approval",
                payload,
            )
            self._emit(
                "task_paused",
                "Task paused awaiting approval",
                payload,
            )
        return payload

    def build_resume_payload(
        self,
        *,
        approval_id: str,
        approved: bool,
        decided_by: str,
        reason: str | None = None,
        edited_arguments: dict[str, Any] | None = None,
    ) -> LangGraphResumePayload:
        return LangGraphResumePayload(
            approval_id=approval_id,
            approved=approved,
            decided_by=decided_by,
            reason=reason,
            edited_arguments=_json_safe(edited_arguments)
            if edited_arguments is not None
            else None,
        )

    def write_jsonl_for_task(self, task_id: str, output_path: Path) -> None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("w", encoding="utf-8") as file:
            for record in self._interrupts_by_task.get(task_id, []):
                file.write(
                    json.dumps(record.model_dump(mode="json"), ensure_ascii=False)
                )
                file.write("\n")

    def _find_existing_pending(
        self,
        *,
        task_id: str,
        tool_name: str,
        arguments: dict[str, Any],
    ):
        safe_arguments = _json_safe(arguments)
        for pending in self.pending_manager.list_for_task(task_id):
            if pending.tool_name == tool_name and pending.arguments == safe_arguments:
                return pending
        return None

    def _new_interrupt_id(self) -> str:
        interrupt_id = f"lg_interrupt_{self._next_interrupt_id:06d}"
        self._next_interrupt_id += 1
        return interrupt_id

    def _emit(
        self,
        kind: str,
        message: str,
        payload: dict[str, Any],
    ) -> None:
        if self.event_sink is None:
            return
        try:
            self.event_sink(kind, message, payload)
        except Exception:
            return


def _coerce_risk_result(value: Any) -> RiskCheckResult:
    if isinstance(value, RiskCheckResult):
        return value
    if isinstance(value, dict):
        return RiskCheckResult.model_validate(value)
    if hasattr(value, "model_dump"):
        return RiskCheckResult.model_validate(value.model_dump(mode="json"))
    raise TypeError(f"Unsupported risk result type: {type(value).__name__}")


def _action_details(arguments: dict[str, Any]) -> tuple[str | None, str | None]:
    action = arguments.get("action")
    if not isinstance(action, dict):
        return None, None
    action_type = action.get("action_type")
    target_hint = action.get("target_hint")
    return (
        str(action_type) if action_type is not None else None,
        str(target_hint) if target_hint is not None else None,
    )


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


def _json_safe(value: Any) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=False, default=str))
