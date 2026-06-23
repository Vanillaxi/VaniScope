from __future__ import annotations

from webscoper.browser.public_web import PublicWebPolicyError
from webscoper.browser.tool_runtime import StatefulBrowserToolRuntime
from webscoper.tools.gateway.descriptors import (
    ToolDescriptor,
    ToolInvocationRequest,
    ToolInvocationResult,
)
from webscoper.tools.gateway.providers.common import (
    bool_arg,
    descriptor_from_registry_tool,
    failed,
    normalize_url,
    optional_int,
    optional_str,
    success,
    tool_output_result,
)
from webscoper.tools.registry import ToolRegistry, create_default_tool_registry


class BrowserToolProvider:
    provider_type = "browser"

    def __init__(
        self,
        browser_runtime: StatefulBrowserToolRuntime,
        tool_registry: ToolRegistry | None = None,
    ) -> None:
        self.browser_runtime = browser_runtime
        self.tool_registry = tool_registry or create_default_tool_registry()

    def list_tools(self) -> list[ToolDescriptor]:
        return [
            descriptor_from_registry_tool(tool, provider_type="browser")
            for tool in self.tool_registry.list_tools()
            if tool.tool_id in {
                "browser_open",
                "browser_observe",
                "browser_click",
                "browser_type",
                "browser_select",
                "browser_scroll",
                "browser_wait",
                "browser_extract",
                "browser_screenshot",
                "ask_human",
                "finish_task",
                "browser_upload_file",
                "browser_download",
                "browser_drag",
            }
        ]

    def get_tool(self, tool_name: str) -> ToolDescriptor | None:
        for tool in self.list_tools():
            if tool.tool_id == tool_name:
                return tool
        return None

    async def invoke(self, request: ToolInvocationRequest) -> ToolInvocationResult:
        if request.tool_name == "browser_open":
            url = normalize_url(str(request.arguments.get("url") or ""))
            try:
                output = await self.browser_runtime.open(
                    url,
                    session_id=optional_str(request.arguments.get("session_id")),
                    wait_until=optional_str(request.arguments.get("wait_until")),
                    reason=optional_str(request.arguments.get("reason")),
                )
            except PublicWebPolicyError as exc:
                output = {"public_web_policy": exc.decision.model_dump(mode="json")}
                if exc.observation is not None:
                    output["observation"] = exc.observation.model_dump(mode="json")
                return failed(
                    request,
                    "browser",
                    "PUBLIC_WEB_BLOCKED",
                    exc.decision.reason,
                    output=output,
                    status="blocked",
                    metadata={"public_web_policy": exc.decision.model_dump(mode="json")},
                )
            return success(request, "browser", output)

        if request.tool_name == "browser_observe":
            output = await self.browser_runtime.observe(
                session_id=optional_str(request.arguments.get("session_id")),
                include_screenshot=bool_arg(request.arguments, "include_screenshot", True),
                include_accessibility=bool_arg(request.arguments, "include_accessibility", True),
                reason=optional_str(request.arguments.get("reason")),
            )
            return success(request, "browser", output)

        if request.tool_name == "browser_click":
            output = await self.browser_runtime.click(
                target_hint=str(request.arguments.get("target_hint") or ""),
                expected_effect=request.arguments.get("expected_effect")
                if isinstance(request.arguments.get("expected_effect"), dict)
                else None,
                session_id=optional_str(request.arguments.get("session_id")),
                reason=optional_str(request.arguments.get("reason")),
            )
            status = str(output.get("status", "success"))
            if status in {"failed", "blocked"}:
                return failed(
                    request,
                    "browser",
                    str(output.get("error_type") or "BROWSER_ACTION_FAILED"),
                    str(output.get("error_message") or "Browser action failed."),
                    output=output,
                    status="blocked" if status == "blocked" else "failed",
                )
            return success(request, "browser", output)

        if request.tool_name == "browser_type":
            output = await self.browser_runtime.type_text(
                target_hint=str(request.arguments.get("target_hint") or ""),
                text=str(request.arguments.get("text") or ""),
                session_id=optional_str(request.arguments.get("session_id")),
                reason=optional_str(request.arguments.get("reason")),
            )
            return tool_output_result(request, output)

        if request.tool_name == "browser_select":
            output = await self.browser_runtime.select_option(
                target_hint=str(request.arguments.get("target_hint") or ""),
                option_text=optional_str(request.arguments.get("option_text")),
                option_value=optional_str(request.arguments.get("option_value")),
                session_id=optional_str(request.arguments.get("session_id")),
                reason=optional_str(request.arguments.get("reason")),
            )
            return tool_output_result(request, output)

        if request.tool_name == "browser_scroll":
            output = await self.browser_runtime.scroll(
                direction=str(request.arguments.get("direction") or "down"),
                amount=str(request.arguments.get("amount") or "medium"),
                session_id=optional_str(request.arguments.get("session_id")),
                reason=optional_str(request.arguments.get("reason")),
            )
            return tool_output_result(request, output)

        if request.tool_name == "browser_wait":
            output = await self.browser_runtime.wait(
                condition=str(request.arguments.get("condition") or "readiness"),
                value=optional_str(request.arguments.get("value")),
                timeout_ms=optional_int(request.arguments.get("timeout_ms")),
                session_id=optional_str(request.arguments.get("session_id")),
                reason=optional_str(request.arguments.get("reason")),
            )
            return tool_output_result(request, output)

        if request.tool_name == "browser_extract":
            output = await self.browser_runtime.extract(
                instruction=optional_str(request.arguments.get("instruction")),
                evidence_mode=optional_str(request.arguments.get("evidence_mode")),
            )
            return tool_output_result(request, output)

        if request.tool_name == "browser_screenshot":
            output = await self.browser_runtime.screenshot(
                session_id=optional_str(request.arguments.get("session_id")),
                reason=optional_str(request.arguments.get("reason")),
            )
            return tool_output_result(request, output)

        if request.tool_name == "ask_human":
            return failed(
                request,
                "browser",
                "ASK_HUMAN_REQUIRED",
                str(request.arguments.get("reason") or "Human input is required."),
                output={
                    "decision": "needs_input",
                    "selected_option": None,
                    "comment": None,
                    "risk_context": request.arguments.get("risk_context"),
                },
                status="blocked",
            )

        if request.tool_name == "finish_task":
            summary = request.arguments.get("summary_instruction") or request.arguments.get("summary")
            output = await self.browser_runtime.finish_task(
                summary=str(summary) if summary is not None else None
            )
            return success(request, "browser", output)

        return failed(
            request,
            "browser",
            "UNSUPPORTED_BROWSER_TOOL",
            f"Unsupported browser tool: {request.tool_name}",
        )
