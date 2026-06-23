from __future__ import annotations

from typing import Any

from webscoper.tools.gateway.descriptors import (
    ToolDescriptor,
    ToolInvocationRequest,
    ToolInvocationResult,
)
from webscoper.tools.gateway.providers.common import failed, local_echo_descriptor, success


class LocalToolProvider:
    provider_type = "local"

    def __init__(
        self,
        tools: list[ToolDescriptor] | None = None,
        handlers: dict[str, Any] | None = None,
    ) -> None:
        self._tools = {tool.tool_id: tool for tool in tools or [local_echo_descriptor()]}
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
            return failed(
                request,
                "local",
                "UNSUPPORTED_LOCAL_TOOL",
                f"Unsupported local tool: {request.tool_name}",
            )
        output = handler(request.arguments)
        return success(request, "local", output if isinstance(output, dict) else {"value": output})
