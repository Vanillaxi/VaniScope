from __future__ import annotations

from typing import Awaitable, Callable

import httpx

from webscoper.browser.public_web import PublicWebPolicy, PublicWebRuntimeConfig
from webscoper.tools.gateway.descriptors import (
    ToolDescriptor,
    ToolInvocationRequest,
    ToolInvocationResult,
)
from webscoper.tools.gateway.providers.common import (
    descriptor_from_registry_tool,
    failed,
    success,
)
from webscoper.tools.gateway.providers.research.extractors import (
    docs_extract_output,
    table_extract_output,
)
from webscoper.tools.gateway.providers.research.github import (
    github_output,
    github_url,
    is_github_url,
)
from webscoper.tools.registry import ToolRegistry, create_default_tool_registry


FetchText = Callable[[str], Awaitable[str]]


class ResearchToolProvider:
    provider_type = "remote"

    def __init__(
        self,
        tool_registry: ToolRegistry | None = None,
        *,
        public_web_config: PublicWebRuntimeConfig | None = None,
        fetch_text: FetchText | None = None,
    ) -> None:
        self.tool_registry = tool_registry or create_default_tool_registry()
        self.public_web_policy = PublicWebPolicy(public_web_config)
        self.fetch_text = fetch_text or fetch_text_http

    def list_tools(self) -> list[ToolDescriptor]:
        return [
            descriptor_from_registry_tool(tool, provider_type="remote")
            for tool in self.tool_registry.list_tools()
            if tool.provider == "research"
        ]

    def get_tool(self, tool_name: str) -> ToolDescriptor | None:
        for tool in self.list_tools():
            if tool.tool_id == tool_name:
                return tool
        return None

    async def invoke(self, request: ToolInvocationRequest) -> ToolInvocationResult:
        if request.tool_name == "github_fetch_issue":
            return await self._fetch_github(request, kind="issue")
        if request.tool_name == "github_fetch_pr":
            return await self._fetch_github(request, kind="pull")
        if request.tool_name == "docs_extract":
            return success(request, "remote", docs_extract_output(request))
        if request.tool_name == "table_extract":
            return success(request, "remote", table_extract_output(request))
        return failed(
            request,
            "remote",
            "UNSUPPORTED_RESEARCH_TOOL",
            f"Unsupported research tool: {request.tool_name}",
        )

    async def _fetch_github(
        self,
        request: ToolInvocationRequest,
        *,
        kind: str,
    ) -> ToolInvocationResult:
        url = github_url(request.arguments, kind=kind)
        if url is None:
            return failed(
                request,
                "remote",
                "INVALID_GITHUB_REFERENCE",
                "Provide a public GitHub URL or repo plus number.",
            )
        if not is_github_url(url, kind=kind):
            return failed(
                request,
                "remote",
                "GITHUB_URL_REQUIRED",
                f"{request.tool_name} only accepts public github.com {kind} URLs.",
                status="blocked",
            )
        decision = self.public_web_policy.check(url)
        if not decision.allow:
            return failed(
                request,
                "remote",
                "PUBLIC_WEB_BLOCKED",
                decision.reason,
                output={"public_web_policy": decision.model_dump(mode="json")},
                status="blocked",
                metadata={"public_web_policy": decision.model_dump(mode="json")},
            )
        html = str(request.arguments.get("html") or "")
        if not html:
            html = await self.fetch_text(url)
        return success(request, "remote", github_output(html, source_url=url, kind=kind))


async def fetch_text_http(url: str) -> str:
    async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
        response = await client.get(url, headers={"User-Agent": "VaniScope/0.1"})
        response.raise_for_status()
        return response.text
