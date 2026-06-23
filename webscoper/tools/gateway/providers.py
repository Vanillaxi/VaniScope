from __future__ import annotations

import re
from html import unescape
from pathlib import Path
from typing import Any, Awaitable, Callable, Protocol
from urllib.parse import urlparse

import httpx

from webscoper.browser.public_web import PublicWebPolicy, PublicWebRuntimeConfig
from webscoper.browser.public_web import PublicWebPolicyError
from webscoper.browser.tool_runtime import StatefulBrowserToolRuntime
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
            url = _normalize_url(str(request.arguments.get("url") or ""))
            try:
                output = await self.browser_runtime.open(
                    url,
                    session_id=_optional_str(request.arguments.get("session_id")),
                    wait_until=_optional_str(request.arguments.get("wait_until")),
                    reason=_optional_str(request.arguments.get("reason")),
                )
            except PublicWebPolicyError as exc:
                output = {"public_web_policy": exc.decision.model_dump(mode="json")}
                if exc.observation is not None:
                    output["observation"] = exc.observation.model_dump(mode="json")
                return _failed(
                    request,
                    "browser",
                    "PUBLIC_WEB_BLOCKED",
                    exc.decision.reason,
                    output=output,
                    status="blocked",
                    metadata={"public_web_policy": exc.decision.model_dump(mode="json")},
                )
            return _success(request, "browser", output)

        if request.tool_name == "browser_observe":
            output = await self.browser_runtime.observe(
                session_id=_optional_str(request.arguments.get("session_id")),
                include_screenshot=_bool_arg(request.arguments, "include_screenshot", True),
                include_accessibility=_bool_arg(request.arguments, "include_accessibility", True),
                reason=_optional_str(request.arguments.get("reason")),
            )
            return _success(request, "browser", output)

        if request.tool_name == "browser_click":
            output = await self.browser_runtime.click(
                target_hint=str(request.arguments.get("target_hint") or ""),
                expected_effect=request.arguments.get("expected_effect")
                if isinstance(request.arguments.get("expected_effect"), dict)
                else None,
                session_id=_optional_str(request.arguments.get("session_id")),
                reason=_optional_str(request.arguments.get("reason")),
            )
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

        if request.tool_name == "browser_type":
            output = await self.browser_runtime.type_text(
                target_hint=str(request.arguments.get("target_hint") or ""),
                text=str(request.arguments.get("text") or ""),
                session_id=_optional_str(request.arguments.get("session_id")),
                reason=_optional_str(request.arguments.get("reason")),
            )
            return _tool_output_result(request, output)

        if request.tool_name == "browser_select":
            output = await self.browser_runtime.select_option(
                target_hint=str(request.arguments.get("target_hint") or ""),
                option_text=_optional_str(request.arguments.get("option_text")),
                option_value=_optional_str(request.arguments.get("option_value")),
                session_id=_optional_str(request.arguments.get("session_id")),
                reason=_optional_str(request.arguments.get("reason")),
            )
            return _tool_output_result(request, output)

        if request.tool_name == "browser_scroll":
            output = await self.browser_runtime.scroll(
                direction=str(request.arguments.get("direction") or "down"),
                amount=str(request.arguments.get("amount") or "medium"),
                session_id=_optional_str(request.arguments.get("session_id")),
                reason=_optional_str(request.arguments.get("reason")),
            )
            return _tool_output_result(request, output)

        if request.tool_name == "browser_wait":
            output = await self.browser_runtime.wait(
                condition=str(request.arguments.get("condition") or "readiness"),
                value=_optional_str(request.arguments.get("value")),
                timeout_ms=_optional_int(request.arguments.get("timeout_ms")),
                session_id=_optional_str(request.arguments.get("session_id")),
                reason=_optional_str(request.arguments.get("reason")),
            )
            return _tool_output_result(request, output)

        if request.tool_name == "browser_extract":
            output = await self.browser_runtime.extract(
                instruction=_optional_str(request.arguments.get("instruction")),
                evidence_mode=_optional_str(request.arguments.get("evidence_mode")),
            )
            return _tool_output_result(request, output)

        if request.tool_name == "browser_screenshot":
            output = await self.browser_runtime.screenshot(
                session_id=_optional_str(request.arguments.get("session_id")),
                reason=_optional_str(request.arguments.get("reason")),
            )
            return _tool_output_result(request, output)

        if request.tool_name == "ask_human":
            return _failed(
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
        self.fetch_text = fetch_text or _fetch_text

    def list_tools(self) -> list[ToolDescriptor]:
        return [
            _descriptor_from_registry_tool(tool, provider_type="remote")
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
            return _success(request, "remote", _docs_extract_output(request))
        if request.tool_name == "table_extract":
            return _success(request, "remote", _table_extract_output(request))
        return _failed(
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
        url = _github_url(request.arguments, kind=kind)
        if url is None:
            return _failed(
                request,
                "remote",
                "INVALID_GITHUB_REFERENCE",
                "Provide a public GitHub URL or repo plus number.",
            )
        if not _is_github_url(url, kind=kind):
            return _failed(
                request,
                "remote",
                "GITHUB_URL_REQUIRED",
                f"{request.tool_name} only accepts public github.com {kind} URLs.",
                status="blocked",
            )
        decision = self.public_web_policy.check(url)
        if not decision.allow:
            return _failed(
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
        return _success(request, "remote", _github_output(html, source_url=url, kind=kind))


def _descriptor_from_registry_tool(tool: Any, provider_type: str) -> ToolDescriptor:
    return ToolDescriptor(
        tool_id=tool.tool_id,
        name=tool.name,
        display_name=tool.display_name or tool.name,
        description=tool.description,
        provider_type=provider_type,
        input_schema={"schema": getattr(tool, "input_schema", {})},
        output_schema={"schema": getattr(tool, "output_schema", {})},
        loading_mode=(
            "disabled" if not tool.enabled or tool.exposure == "disabled" else tool.loading_mode
        )
        if tool.loading_mode in {"core", "contextual", "lazy", "disabled"}
        else "core",
        provider=tool.provider,
        permission=tool.permission,
        risk_level=tool.risk_level,
        required_context=list(getattr(tool, "required_context", [])),
        schema_summary=dict(getattr(tool, "schema_summary", {})),
        supported_modes=list(getattr(tool, "supported_modes", [])),
        requires_session=tool.requires_session,
        produces_evidence=tool.produces_evidence,
        produces_screenshot=tool.produces_screenshot,
        can_mutate_page=tool.can_mutate_page,
        can_submit_external=tool.can_submit_external,
        public_web_allowed=tool.public_web_allowed,
        local_fixture_allowed=tool.local_fixture_allowed,
        compatibility_wrapper=tool.compatibility_wrapper,
        enabled=tool.enabled,
        exposure=tool.exposure,
        public_web_exposure=tool.public_web_exposure,
        local_fixture_exposure=tool.local_fixture_exposure,
        real_llm_prompt_allowed=tool.real_llm_prompt_allowed,
        tags=list(tool.tags),
        reason_if_disabled=tool.reason_if_disabled,
    )


def _local_echo_descriptor() -> ToolDescriptor:
    return ToolDescriptor(
        tool_id="local_echo",
        name="Local Echo",
        description="Return local echo output for gateway tests.",
        provider_type="local",
    )


async def _fetch_text(url: str) -> str:
    async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
        response = await client.get(url, headers={"User-Agent": "VaniScope/0.1"})
        response.raise_for_status()
        return response.text


def _github_url(arguments: dict[str, Any], *, kind: str) -> str | None:
    url = _optional_str(arguments.get("url"))
    if url:
        return url
    repo = _optional_str(arguments.get("repo"))
    number = _optional_int(arguments.get("number"))
    if not repo or number is None:
        return None
    path = "pull" if kind == "pull" else "issues"
    return f"https://github.com/{repo.strip('/')}/{path}/{number}"


def _is_github_url(url: str, *, kind: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or parsed.hostname != "github.com":
        return False
    parts = [part for part in parsed.path.split("/") if part]
    marker = "pull" if kind == "pull" else "issues"
    return len(parts) >= 4 and parts[2] == marker and parts[3].isdigit()


def _github_output(html: str, *, source_url: str, kind: str) -> dict[str, Any]:
    text = _visible_text(html)
    title = _first_non_empty(
        _meta_content(html, "og:title"),
        _tag_text(html, "title"),
        _heading_text(html),
    )
    labels = _labels(html, text)
    comments = _comments_excerpt(text)
    return {
        "kind": kind,
        "title": title or "Untitled GitHub item",
        "state": _state(text),
        "labels": labels,
        "author": _author(text),
        "body_text": _compact_text(text, limit=6000),
        "comments_excerpt": comments,
        "source_url": source_url,
        "status": "success",
    }


def _docs_extract_output(request: ToolInvocationRequest) -> dict[str, Any]:
    html = _text_arg(request, "html")
    text = _text_arg(request, "text") or _page_observation_text(request)
    source_url = _text_arg(request, "url") or _page_observation_value(request, "url")
    title = _page_observation_value(request, "title")
    if html:
        text = _visible_text(html)
        title = title or _first_non_empty(_tag_text(html, "title"), _heading_text(html))
    query = _text_arg(request, "query")
    matched_excerpt = _matched_excerpt(text, query) if query else _compact_text(text, limit=600)
    return {
        "source_url": source_url,
        "title": title,
        "content_text": _compact_text(text, limit=10000),
        "matched_excerpt": matched_excerpt,
        "status": "success",
    }


def _table_extract_output(request: ToolInvocationRequest) -> dict[str, Any]:
    html = _text_arg(request, "html")
    text = _text_arg(request, "text") or _page_observation_text(request)
    tables = _html_tables(html) if html else _text_tables(text)
    return {
        "source_url": _text_arg(request, "url") or _page_observation_value(request, "url"),
        "tables": tables,
        "table_count": len(tables),
        "status": "success",
    }


def _html_tables(html: str) -> list[dict[str, Any]]:
    tables: list[dict[str, Any]] = []
    for table_html in re.findall(r"<table\b[^>]*>(.*?)</table>", html, flags=re.I | re.S):
        rows: list[list[str]] = []
        for row_html in re.findall(r"<tr\b[^>]*>(.*?)</tr>", table_html, flags=re.I | re.S):
            cells = re.findall(r"<t[hd]\b[^>]*>(.*?)</t[hd]>", row_html, flags=re.I | re.S)
            if cells:
                rows.append([_visible_text(cell).strip() for cell in cells])
        if not rows:
            continue
        headers = rows[0]
        data_rows = rows[1:] if len(rows) > 1 else []
        tables.append(
            {
                "headers": headers,
                "rows": [
                    {headers[index] if index < len(headers) else f"column_{index + 1}": value for index, value in enumerate(row)}
                    for row in data_rows
                ],
            }
        )
    return tables


def _text_tables(text: str) -> list[dict[str, Any]]:
    lines = [line.strip() for line in text.splitlines() if "|" in line]
    if len(lines) < 2:
        return []
    headers = [cell.strip() for cell in lines[0].strip("|").split("|")]
    rows = []
    for line in lines[1:]:
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) == len(headers):
            rows.append(dict(zip(headers, cells, strict=False)))
    return [{"headers": headers, "rows": rows}] if rows else []


def _visible_text(html: str) -> str:
    without_scripts = re.sub(r"<(script|style)\b[^>]*>.*?</\1>", " ", html, flags=re.I | re.S)
    text = re.sub(r"<[^>]+>", " ", without_scripts)
    return _compact_whitespace(unescape(text))


def _tag_text(html: str, tag: str) -> str | None:
    match = re.search(rf"<{tag}\b[^>]*>(.*?)</{tag}>", html, flags=re.I | re.S)
    return _visible_text(match.group(1)) if match else None


def _heading_text(html: str) -> str | None:
    for level in range(1, 4):
        value = _tag_text(html, f"h{level}")
        if value:
            return value
    return None


def _meta_content(html: str, property_name: str) -> str | None:
    match = re.search(
        rf'<meta\b[^>]*(?:property|name)=["\']{re.escape(property_name)}["\'][^>]*content=["\']([^"\']+)["\']',
        html,
        flags=re.I,
    )
    return unescape(match.group(1)).strip() if match else None


def _labels(html: str, text: str) -> list[str]:
    html_labels = [
        _visible_text(match).strip()
        for match in re.findall(r'class=["\'][^"\']*label[^"\']*["\'][^>]*>(.*?)</', html, flags=re.I | re.S)
    ]
    if html_labels:
        return _unique_non_empty(html_labels)[:20]
    section = re.search(r"Labels\s+(.+?)(?:Issue Body|Expected Behavior|Current Behavior|$)", text, flags=re.I)
    if not section:
        return []
    return _unique_non_empty(re.split(r"\s{2,}|,\s*", section.group(1)))[:20]


def _state(text: str) -> str | None:
    match = re.search(r"\b(open|closed|merged)\b", text, flags=re.I)
    return match.group(1).lower() if match else None


def _author(text: str) -> str | None:
    match = re.search(r"(?:Author|Maintainer):\s*([^\n\.]+)", text, flags=re.I)
    return match.group(1).strip() if match else None


def _comments_excerpt(text: str) -> list[str]:
    excerpts = []
    for label in ("Maintainer Comments", "Comments", "Review"):
        match = re.search(rf"{label}\s+(.+?)(?:Acceptance Criteria|Risks|$)", text, flags=re.I)
        if match:
            excerpts.append(_compact_text(match.group(1), limit=600))
    return excerpts[:5]


def _matched_excerpt(text: str, query: str | None) -> str | None:
    if not query:
        return None
    terms = [term.lower() for term in re.findall(r"[a-zA-Z0-9_]+", query) if len(term) > 2]
    sentences = re.split(r"(?<=[.!?])\s+", text)
    for sentence in sentences:
        lowered = sentence.lower()
        if any(term in lowered for term in terms):
            return _compact_text(sentence, limit=600)
    return _compact_text(text, limit=600)


def _page_observation_text(request: ToolInvocationRequest) -> str:
    observation = request.page_observation if isinstance(request.page_observation, dict) else {}
    return _compact_whitespace(
        str(
            observation.get("visible_text_summary")
            or observation.get("main_content_summary")
            or observation.get("accessibility_summary")
            or ""
        )
    )


def _page_observation_value(request: ToolInvocationRequest, key: str) -> str | None:
    observation = request.page_observation if isinstance(request.page_observation, dict) else {}
    value = observation.get(key)
    return str(value) if value else None


def _text_arg(request: ToolInvocationRequest, key: str) -> str:
    value = request.arguments.get(key)
    return str(value) if value else ""


def _first_non_empty(*values: str | None) -> str | None:
    for value in values:
        if value and value.strip():
            return value.strip()
    return None


def _unique_non_empty(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        normalized = _compact_whitespace(value).strip()
        key = normalized.lower()
        if normalized and key not in seen:
            seen.add(key)
            result.append(normalized)
    return result


def _compact_text(text: str, *, limit: int) -> str:
    compacted = _compact_whitespace(text)
    if len(compacted) <= limit:
        return compacted
    return compacted[: limit - 14].rstrip() + " [truncated]"


def _compact_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _normalize_url(value: str) -> str:
    if urlparse(value).scheme:
        return value
    return Path(value).resolve().as_uri()


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if text else None


def _optional_int(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None


def _bool_arg(arguments: dict[str, Any], key: str, default: bool) -> bool:
    value = arguments.get(key, default)
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in {"1", "true", "yes", "on"}
    return default


def _tool_output_result(
    request: ToolInvocationRequest,
    output: dict[str, Any],
) -> ToolInvocationResult:
    status = str(output.get("status", "success"))
    if status in {"failed", "blocked", "timeout"}:
        return _failed(
            request,
            "browser",
            str(output.get("error_type") or "BROWSER_TOOL_FAILED"),
            str(output.get("error_message") or output.get("message") or "Browser tool failed."),
            output=output,
            status="blocked" if status == "blocked" else "failed",
        )
    return _success(request, "browser", output)


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
    metadata: dict[str, Any] | None = None,
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
        metadata=metadata or {},
    )
