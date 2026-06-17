from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from webscoper.schemas.action import ActionContract
from webscoper.schemas.context import WebAgentContextSnapshot
from webscoper.schemas.tool_call import ToolCall, ToolResult
from webscoper.tools.browser_tools import StatefulBrowserToolRuntime
from webscoper.tools.registry import ToolRegistry


class LocalToolExecutor:
    def __init__(
        self,
        tool_registry: ToolRegistry,
        browser_runtime: StatefulBrowserToolRuntime,
    ) -> None:
        self.tool_registry = tool_registry
        self.browser_runtime = browser_runtime

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
