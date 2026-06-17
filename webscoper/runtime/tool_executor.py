from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from webscoper.runtime.approvals import ApprovalStore
from webscoper.runtime.events import TaskEventSink
from webscoper.runtime.risk_gate import RiskGate
from webscoper.schemas.action import ActionContract
from webscoper.schemas.context import WebAgentContextSnapshot
from webscoper.schemas.risk import RiskCheckResult
from webscoper.schemas.tool_call import ToolCall, ToolResult
from webscoper.tools.browser_tools import StatefulBrowserToolRuntime
from webscoper.tools.registry import ToolRegistry


class LocalToolExecutor:
    def __init__(
        self,
        tool_registry: ToolRegistry,
        browser_runtime: StatefulBrowserToolRuntime,
        risk_gate: RiskGate | None = None,
        approval_store: ApprovalStore | None = None,
        event_sink: TaskEventSink | None = None,
    ) -> None:
        self.tool_registry = tool_registry
        self.browser_runtime = browser_runtime
        self.risk_gate = risk_gate or RiskGate()
        self.approval_store = approval_store or ApprovalStore()
        self.event_sink = event_sink

    async def execute(
        self,
        call: ToolCall,
        context: WebAgentContextSnapshot,
    ) -> ToolResult:
        started_at = _utc_now()
        tool = self.tool_registry.get(call.tool_id)
        if tool is None:
            return _result(
                call,
                started_at,
                status="failed",
                error_type="UNKNOWN_TOOL",
                error_message=f"Unknown tool: {call.tool_id}",
            )

        if tool.loading_mode == "lazy":
            return _result(
                call,
                started_at,
                status="failed",
                error_type="LAZY_TOOL_NOT_LOADED",
                error_message=(
                    "Lazy tools are registered for search and prompt display only in this phase."
                ),
            )

        if tool.tool_type != "local":
            return _result(
                call,
                started_at,
                status="failed",
                error_type="UNSUPPORTED_TOOL_TYPE",
                error_message=f"Unsupported tool type: {tool.tool_type}",
            )

        if context.safety.mode == "read_only" and tool.risk_level != "read_only":
            return _result(
                call,
                started_at,
                status="blocked",
                error_type="TOOL_BLOCKED_BY_SAFETY",
                error_message=f"Tool {call.tool_id} is blocked by read_only safety mode.",
            )

        risk_result = self.risk_gate.check_tool_call(
            task_id=context.trace.run_id,
            tool_name=call.tool_id,
            arguments=call.arguments,
            page_observation=self.browser_runtime.last_observation,
        )
        if not risk_result.allowed:
            return self._risk_result(call, context, started_at, risk_result)

        try:
            output = await self._execute_local(call)
            status = str(output.get("status", "success"))
            return _result(
                call,
                started_at,
                status=status,
                output=output,
                error_type=output.get("error_type"),
                error_message=output.get("error_message"),
            )
        except Exception as exc:
            return _result(
                call,
                started_at,
                status="failed",
                error_type=type(exc).__name__,
                error_message=str(exc),
            )

    async def _execute_local(self, call: ToolCall) -> dict[str, Any]:
        if call.tool_id == "browser_open_observe":
            observation = await self.browser_runtime.open_observe(
                str(call.arguments.get("url") or "")
            )
            return {
                "status": "success",
                "observation": observation.model_dump(mode="json"),
            }

        if call.tool_id == "browser_click_intent":
            action_payload = call.arguments.get("action")
            if not isinstance(action_payload, dict):
                return {
                    "status": "failed",
                    "error_type": "ACTION_REQUIRED",
                    "error_message": "browser_click_intent requires arguments.action.",
                }
            action = ActionContract.model_validate(action_payload)
            return await self.browser_runtime.click_intent(action)

        if call.tool_id == "browser_extract":
            return await self.browser_runtime.extract()

        if call.tool_id == "finish_task":
            summary = call.arguments.get("summary")
            return await self.browser_runtime.finish_task(
                summary=str(summary) if summary is not None else None
            )

        return {
            "status": "failed",
            "error_type": "UNSUPPORTED_LOCAL_TOOL",
            "error_message": f"Unsupported local tool: {call.tool_id}",
        }

    def _risk_result(
        self,
        call: ToolCall,
        context: WebAgentContextSnapshot,
        started_at: str,
        risk_result: RiskCheckResult,
    ) -> ToolResult:
        task_id = context.trace.run_id
        action_payload = call.arguments.get("action")
        action_type: str | None = None
        target_hint: str | None = None
        if isinstance(action_payload, dict):
            action_type = _str_or_none(action_payload.get("action_type"))
            target_hint = _str_or_none(action_payload.get("target_hint"))

        approval = None
        if risk_result.requires_approval:
            approval = self.approval_store.create_request(
                task_id=task_id,
                reason=risk_result.reason,
                risk_level=risk_result.risk_level,
                tool_name=call.tool_id,
                action_type=action_type,
                target_hint=target_hint,
                metadata={
                    "risk_check": risk_result.model_dump(mode="json"),
                    "call": call.model_dump(mode="json"),
                },
            )
            risk_result = risk_result.model_copy(
                update={"approval_request_id": approval.approval_id}
            )

        self.approval_store.record_check(task_id, risk_result)
        self._write_risk_artifacts(context)

        event_payload = {
            "run_id": task_id,
            "tool_name": call.tool_id,
            "risk_check": risk_result.model_dump(mode="json"),
            "approval_request": approval.model_dump(mode="json") if approval else None,
        }
        if risk_result.requires_approval:
            self._emit_event(
                "approval_required",
                "Approval required before tool execution",
                event_payload,
            )
            return _result(
                call,
                started_at,
                status="blocked",
                output=event_payload,
                error_type="RISK_APPROVAL_REQUIRED",
                error_message=risk_result.reason,
            )

        self._emit_event(
            "risk_blocked",
            "Risk gate blocked tool execution",
            event_payload,
        )
        return _result(
            call,
            started_at,
            status="blocked",
            output=event_payload,
            error_type="RISK_BLOCKED",
            error_message=risk_result.reason,
        )

    def _write_risk_artifacts(self, context: WebAgentContextSnapshot) -> None:
        run_dir = Path(context.trace.run_dir)
        try:
            self.approval_store.write_jsonl_for_task(
                context.trace.run_id,
                run_dir / "approvals.jsonl",
            )
            self.approval_store.write_risk_report(
                context.trace.run_id,
                run_dir / "risk_report.json",
            )
        except Exception:
            return

    def _emit_event(
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


def _result(
    call: ToolCall,
    started_at: str,
    status: str,
    output: dict[str, Any] | None = None,
    error_type: str | None = None,
    error_message: str | None = None,
) -> ToolResult:
    return ToolResult(
        call_id=call.call_id,
        tool_id=call.tool_id,
        status=status,
        output=output or {},
        error_type=error_type,
        error_message=error_message,
        started_at=started_at,
        ended_at=_utc_now(),
    )


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _str_or_none(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)
