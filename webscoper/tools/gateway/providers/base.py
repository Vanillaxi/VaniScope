from __future__ import annotations

from typing import Protocol

from webscoper.tools.gateway.descriptors import (
    ToolDescriptor,
    ToolInvocationRequest,
    ToolInvocationResult,
)


class ToolProvider(Protocol):
    provider_type: str

    def list_tools(self) -> list[ToolDescriptor]:
        ...

    def get_tool(self, tool_name: str) -> ToolDescriptor | None:
        ...

    async def invoke(self, request: ToolInvocationRequest) -> ToolInvocationResult:
        ...
