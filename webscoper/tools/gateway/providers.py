from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol

from webscoper.browser.tool_runtime import StatefulBrowserToolRuntime
from webscoper.schemas.browser import ActionContract
from webscoper.tools.gateway.descriptors import (
    ToolDescriptor,
    ToolInvocationRequest,
    ToolInvocationResult,
)
from webscoper.tools.registry import ToolRegistry, create_default_tool_registry


class ToolProvider(Protocol):
    provider_type: str

    def list_tools(self) -> list[ToolDescriptor]:
        ...

    def get_tool(self, tool_name: str) -> ToolDescriptor | None:
        ...

    async def invoke(self, request: ToolInvocationRequest) -> ToolInvocationResult:
        ...


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
            _descriptor_from_registry_tool(tool, provider_type="browser")
            for tool in self.tool_registry.list_tools()
            if tool.tool_id in {
                "browser_open_observe",
                "browser_click_intent",
                "browser_extract",
                "finish_task",
            }
        ]

    def get_tool(self, tool_name: str) -> ToolDescriptor | None:
        for tool in self.list_tools():
            if tool.tool_id == tool_name:
                return tool
        return None

    async def invoke(self, request: ToolInvocationRequest) -> ToolInvocationResult:
        if request.tool_name == "browser_open_observe":
            url = _normalize_url(str(request.arguments.get("url") or ""))
            observation = await self.browser_runtime.open_observe(
                url
            )
            return _success(request, "browser", {"observation": observation.model_dump(mode="json")})

        if request.tool_name == "browser_click_intent":
            action_payload = request.arguments.get("action")
            if not isinstance(action_payload, dict):
                return _failed(
                    request,
                    "browser",
                    "ACTION_REQUIRED",
                    "browser_click_intent requires arguments.action.",
                )
            action = ActionContract.model_validate(action_payload)
            output = await self.browser_runtime.click_intent(action)
            status = str(output.get("status", "success"))
            if status in {"failed", "blocked"}:
                return _failed(
                    request,
                    "browser",
                    str(output.get("error_type") or "BROWSER_ACTION_FAILED"),
                    str(output.get("error_message") or "Browser action failed."),
                    output=output,
                    status="blocked" if status == "blocked" else "failed",
                )
            return _success(request, "browser", output)

        if request.tool_name == "browser_extract":
            output = await self.browser_runtime.extract()
            return _success(request, "browser", output)

        if request.tool_name == "finish_task":
            summary = request.arguments.get("summary")
            output = await self.browser_runtime.finish_task(
                summary=str(summary) if summary is not None else None
            )
            return _success(request, "browser", output)

        return _failed(
            request,
            "browser",
            "UNSUPPORTED_BROWSER_TOOL",
            f"Unsupported browser tool: {request.tool_name}",
        )


class LocalToolProvider:
    provider_type = "local"

    def __init__(
        self,
        tools: list[ToolDescriptor] | None = None,
        handlers: dict[str, Any] | None = None,
    ) -> None:
        self._tools = {tool.tool_id: tool for tool in tools or [_local_echo_descriptor()]}
        self._handlers = handlers or {
            "local_echo": lambda arguments: {"echo": arguments.get("text", "")}
        }

    def list_tools(self) -> list[ToolDescriptor]:
        return list(self._tools.values())

    def get_tool(self, tool_name: str) -> ToolDescriptor | None:
        return self._tools.get(tool_name)

    async def invoke(self, request: ToolInvocationRequest) -> ToolInvocationResult:
        handler = self._handlers.get(request.tool_name)
        if handler is None:
            return _failed(
                request,
                "local",
                "UNSUPPORTED_LOCAL_TOOL",
                f"Unsupported local tool: {request.tool_name}",
            )
        output = handler(request.arguments)
        return _success(request, "local", output if isinstance(output, dict) else {"value": output})


class FakeMCPToolProvider:
    provider_type = "mcp"

    def __init__(self) -> None:
        self._tools = {
            tool.tool_id: tool
            for tool in [
                ToolDescriptor(
                    tool_id="fake_mcp_echo",
                    name="Fake MCP Echo",
                    description="Return the provided text deterministically.",
                    provider_type="mcp",
                    tags=["fake", "mcp", "echo"],
                ),
                ToolDescriptor(
                    tool_id="fake_mcp_get_time",
                    name="Fake MCP Get Time",
                    description="Return a deterministic timestamp for tests.",
                    provider_type="mcp",
                    tags=["fake", "mcp", "time"],
                ),
                ToolDescriptor(
                    tool_id="fake_mcp_fetch_doc",
                    name="Fake MCP Fetch Doc",
                    description="Return deterministic local documentation text.",
                    provider_type="mcp",
                    tags=["fake", "mcp", "docs"],
                    lazy=True,
                ),
                ToolDescriptor(
                    tool_id="fake_mcp_disabled",
                    name="Fake MCP Disabled",
                    description="Disabled fake MCP tool for policy tests.",
                    provider_type="mcp",
                    enabled=False,
                    tags=["fake", "mcp", "disabled"],
                ),
                ToolDescriptor(
                    tool_id="fake_mcp_delete_data",
                    name="Fake MCP Delete Data",
                    description="Dangerous fake MCP tool that must be blocked.",
                    provider_type="mcp",
                    permission="dangerous",
                    risk_level="dangerous",
                    tags=["fake", "mcp", "dangerous"],
                ),
            ]
        }

    def list_tools(self) -> list[ToolDescriptor]:
        return list(self._tools.values())

    def get_tool(self, tool_name: str) -> ToolDescriptor | None:
        return self._tools.get(tool_name)

    async def invoke(self, request: ToolInvocationRequest) -> ToolInvocationResult:
        if request.tool_name == "fake_mcp_echo":
            return _success(
                request,
                "mcp",
                {"text": str(request.arguments.get("text") or "")},
            )
        if request.tool_name == "fake_mcp_get_time":
            return _success(
                request,
                "mcp",
                {"iso_time": "2026-01-01T00:00:00+00:00"},
            )
        if request.tool_name == "fake_mcp_fetch_doc":
            topic = str(request.arguments.get("topic") or "tool_gateway")
            return _success(
                request,
                "mcp",
                {
                    "topic": topic,
                    "content": f"Fake MCP documentation for {topic}.",
                },
            )
        return _failed(
            request,
            "mcp",
            "UNKNOWN_FAKE_MCP_TOOL",
            f"Unknown fake MCP tool: {request.tool_name}",
        )


def _descriptor_from_registry_tool(tool: Any, provider_type: str) -> ToolDescriptor:
    return ToolDescriptor(
        tool_id=tool.tool_id,
        name=tool.name,
        description=tool.description,
        provider_type=provider_type,
        permission="read_only",
        risk_level="read_only",
        lazy=tool.loading_mode == "lazy",
        enabled=True,
        tags=list(tool.tags),
    )


def _local_echo_descriptor() -> ToolDescriptor:
    return ToolDescriptor(
        tool_id="local_echo",
        name="Local Echo",
        description="Return local echo output for gateway tests.",
        provider_type="local",
    )


def _normalize_url(value: str) -> str:
    if value.startswith(("http://", "https://", "file://")):
        return value
    return Path(value).resolve().as_uri()


def _success(
    request: ToolInvocationRequest,
    provider_type: str,
    output: dict[str, Any],
) -> ToolInvocationResult:
    return ToolInvocationResult(
        task_id=request.task_id,
        tool_name=request.tool_name,
        call_id=request.call_id,
        provider_type=provider_type,
        decision="allowed",
        status="success",
        output=output,
    )


def _failed(
    request: ToolInvocationRequest,
    provider_type: str,
    error_type: str,
    error_message: str,
    *,
    output: dict[str, Any] | None = None,
    status: str = "failed",
) -> ToolInvocationResult:
    return ToolInvocationResult(
        task_id=request.task_id,
        tool_name=request.tool_name,
        call_id=request.call_id,
        provider_type=provider_type,
        decision="blocked" if status == "blocked" else "allowed",
        status=status,
        output=output or {},
        error_type=error_type,
        error_message=error_message,
    )
