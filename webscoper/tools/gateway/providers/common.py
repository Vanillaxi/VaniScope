from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from webscoper.tools.gateway.descriptors import (
    ToolDescriptor,
    ToolInvocationRequest,
    ToolInvocationResult,
)


def descriptor_from_registry_tool(tool: Any, provider_type: str) -> ToolDescriptor:
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


def local_echo_descriptor() -> ToolDescriptor:
    return ToolDescriptor(
        tool_id="local_echo",
        name="Local Echo",
        description="Return local echo output for gateway tests.",
        provider_type="local",
    )


def normalize_url(value: str) -> str:
    if urlparse(value).scheme:
        return value
    return Path(value).resolve().as_uri()


def optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if text else None


def optional_int(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None


def bool_arg(arguments: dict[str, Any], key: str, default: bool) -> bool:
    value = arguments.get(key, default)
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in {"1", "true", "yes", "on"}
    return default


def tool_output_result(
    request: ToolInvocationRequest,
    output: dict[str, Any],
) -> ToolInvocationResult:
    status = str(output.get("status", "success"))
    if status in {"failed", "blocked", "timeout"}:
        return failed(
            request,
            "browser",
            str(output.get("error_type") or "BROWSER_TOOL_FAILED"),
            str(output.get("error_message") or output.get("message") or "Browser tool failed."),
            output=output,
            status="blocked" if status == "blocked" else "failed",
        )
    return success(request, "browser", output)


def success(
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


def failed(
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
