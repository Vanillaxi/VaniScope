from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Any

from pydantic import BaseModel

from webscoper.runtime.execution.events import TaskEventSink
from webscoper.runtime.safety.approvals import ApprovalStore
from webscoper.runtime.safety.approvals import PendingApprovalManager
from webscoper.schemas.runtime import RiskCheckResult
from webscoper.tools.gateway.descriptors import (
    ToolDescriptor,
    ToolInvocationRequest,
    ToolInvocationResult,
)
from webscoper.tools.gateway.policy import ToolGatewayPolicy
from webscoper.tools.gateway.providers import ToolProvider


class ToolAuditEvent(BaseModel):
    timestamp: str
    task_id: str
    workflow_backend: str
    tool_name: str
    provider_type: str | None = None
    permission: str | None = None
    risk_level: str | None = None
    decision: str
    status: str
    error_type: str | None = None
    error_message: str | None = None
    duration_ms: float | None = None
    approval_id: str | None = None
    metadata: dict[str, Any] = {}


class ToolGatewayAuditStore:
    def __init__(self, output_path: Path | None = None) -> None:
        self.output_path = output_path
        self.events: list[ToolAuditEvent] = []

    def append(self, event: ToolAuditEvent) -> None:
        self.events.append(event)
        if self.output_path is None:
            return
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        with self.output_path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(event.model_dump(mode="json"), ensure_ascii=False))
            file.write("\n")


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


class ToolGateway:
    def __init__(
        self,
        providers: list[ToolProvider],
        *,
        policy: ToolGatewayPolicy | None = None,
        audit_store: ToolGatewayAuditStore | None = None,
        approval_store: ApprovalStore | None = None,
        pending_manager: PendingApprovalManager | None = None,
        event_sink: TaskEventSink | None = None,
    ) -> None:
        self.providers = providers
        self.policy = policy or ToolGatewayPolicy()
        self.audit_store = audit_store or ToolGatewayAuditStore()
        self.approval_store = approval_store or ApprovalStore()
        self.pending_manager = pending_manager or PendingApprovalManager()
        self.event_sink = event_sink

    def list_tools(self) -> list[ToolDescriptor]:
        tools: list[ToolDescriptor] = [_tool_search_descriptor()]
        for provider in self.providers:
            tools.extend(provider.list_tools())
        return tools

    def search_tools(
        self,
        query: str,
        *,
        context: dict[str, Any] | None = None,
        limit: int = 5,
    ) -> list[ToolDescriptor]:
        normalized = query.lower().strip()
        if not normalized:
            return []
        self._emit(
            "lazy_tool_search_started",
            "Lazy tool search started",
            {
                "task_id": _context_task_id(context),
                "query": query,
                "limit": limit,
            },
        )
        matches: list[ToolDescriptor] = []
        for tool in self.list_tools():
            if not _searchable_lazy_tool(tool):
                continue
            haystack = " ".join(
                [tool.tool_id, tool.name, tool.description, " ".join(tool.tags)]
            ).lower()
            if normalized in haystack or all(term in haystack for term in normalized.split()):
                matches.append(tool)
            if len(matches) >= limit:
                break
        self._emit(
            "lazy_tool_search_finished",
            "Lazy tool search finished",
            {
                "task_id": _context_task_id(context),
                "query": query,
                "match_ids": [tool.tool_id for tool in matches],
            },
        )
        return matches

    def get_tool(self, tool_name: str) -> ToolDescriptor:
        descriptor, _provider = self._resolve(tool_name)
        if descriptor is None:
            raise KeyError(f"Unknown tool: {tool_name}")
        return descriptor

    def get_tool_schema(self, tool_name: str) -> dict[str, Any]:
        return self.get_tool(tool_name).model_dump(mode="json")

    def load_tool(
        self,
        tool_name: str,
        *,
        context: dict[str, Any] | None = None,
    ) -> ToolDescriptor:
        descriptor = self.get_tool(tool_name)
        if not _loadable_tool(descriptor):
            self._emit(
                "lazy_tool_rejected",
                "Lazy tool rejected",
                {
                    "task_id": _context_task_id(context),
                    "tool_name": tool_name,
                    "reason": descriptor.reason_if_disabled or descriptor.exposure,
                },
            )
            raise PermissionError(f"Tool cannot be loaded: {tool_name}")
        self._emit(
            "lazy_tool_loaded",
            "Lazy tool loaded",
            {
                "task_id": _context_task_id(context),
                "tool_name": descriptor.tool_id,
                "provider": descriptor.provider,
                "risk_level": descriptor.risk_level,
            },
        )
        return descriptor

    async def invoke(self, request: ToolInvocationRequest) -> ToolInvocationResult:
        started = perf_counter()
        started_at = utc_now()
        descriptor, provider = self._resolve(request.tool_name)
        self._emit(
            "risk_check_started",
            "Risk check started",
            {
                "task_id": request.task_id,
                "tool_name": request.tool_name,
                "call_id": request.call_id,
            },
        )
        policy_decision = self.policy.check(
            descriptor=descriptor,
            task_id=request.task_id,
            tool_name=request.tool_name,
            arguments=request.arguments,
            page_observation=request.page_observation,
            approval_override_id=request.approval_override_id,
        )
        self._emit(
            "tool_policy_checked",
            "Tool policy checked",
            {
                "task_id": request.task_id,
                "tool_name": request.tool_name,
                "call_id": request.call_id,
                "decision": policy_decision.decision,
                "error_type": policy_decision.error_type,
                "error_message": policy_decision.error_message,
                "risk_check": policy_decision.risk_check.model_dump(mode="json")
                if policy_decision.risk_check is not None
                else None,
            },
        )
        self._emit(
            "risk_check_finished",
            "Risk check finished",
            {
                "task_id": request.task_id,
                "tool_name": request.tool_name,
                "call_id": request.call_id,
                "status": policy_decision.decision,
                "risk_check": policy_decision.risk_check.model_dump(mode="json")
                if policy_decision.risk_check is not None
                else None,
            },
        )

        if request.tool_name == "tool_search":
            result = self._invoke_tool_search(request, descriptor, started_at)
            return self._finish(request, descriptor, result, started, policy_decision.risk_check)

        if policy_decision.decision == "blocked" or descriptor is None or provider is None:
            if descriptor is not None and descriptor.loading_mode == "lazy":
                self._emit(
                    "lazy_tool_rejected",
                    "Lazy tool rejected",
                    {
                        "task_id": request.task_id,
                        "tool_name": request.tool_name,
                        "call_id": request.call_id,
                        "error_type": policy_decision.error_type,
                    },
                )
            result = ToolInvocationResult(
                task_id=request.task_id,
                tool_name=request.tool_name,
                call_id=request.call_id,
                provider_type=descriptor.provider_type if descriptor else None,
                decision="blocked",
                status="blocked",
                error_type=policy_decision.error_type or "TOOL_BLOCKED",
                error_message=policy_decision.error_message or "Tool invocation blocked.",
                started_at=started_at,
            )
            return self._finish(request, descriptor, result, started, policy_decision.risk_check)

        if policy_decision.decision == "approval_required":
            approval_id = self._create_approval_request(
                request,
                descriptor,
                policy_decision.risk_check,
                policy_decision.error_message,
            )
            self._emit(
                "approval_required",
                "Approval required before tool execution",
                {
                    "task_id": request.task_id,
                    "tool_name": request.tool_name,
                    "call_id": request.call_id,
                    "approval_id": approval_id,
                    "risk_check": policy_decision.risk_check.model_dump(mode="json")
                    if policy_decision.risk_check is not None
                    else None,
                },
            )
            result = ToolInvocationResult(
                task_id=request.task_id,
                tool_name=request.tool_name,
                call_id=request.call_id,
                provider_type=descriptor.provider_type,
                decision="approval_required",
                status="approval_required",
                error_type=policy_decision.error_type,
                error_message=policy_decision.error_message,
                approval_id=approval_id,
                output={
                    "approval_id": approval_id,
                    "risk_check": policy_decision.risk_check.model_dump(mode="json")
                    if policy_decision.risk_check is not None
                    else None,
                },
                started_at=started_at,
            )
            return self._finish(request, descriptor, result, started, policy_decision.risk_check)

        try:
            if descriptor.loading_mode == "lazy":
                self._emit(
                    "lazy_tool_execution_started",
                    "Lazy tool execution started",
                    {
                        "task_id": request.task_id,
                        "tool_name": request.tool_name,
                        "call_id": request.call_id,
                    },
                )
            result = await provider.invoke(request)
        except Exception as exc:
            result = ToolInvocationResult(
                task_id=request.task_id,
                tool_name=request.tool_name,
                call_id=request.call_id,
                provider_type=descriptor.provider_type,
                decision="allowed",
                status="failed",
                error_type=type(exc).__name__,
                error_message=str(exc),
                started_at=started_at,
            )
        result.decision = "blocked" if result.status == "blocked" else "allowed"
        result.provider_type = descriptor.provider_type
        result.approval_id = request.approval_override_id
        result.started_at = result.started_at or started_at
        finished = self._finish(request, descriptor, result, started, policy_decision.risk_check)
        if descriptor.loading_mode == "lazy":
            self._emit(
                "lazy_tool_execution_finished",
                "Lazy tool execution finished",
                {
                    "task_id": request.task_id,
                    "tool_name": request.tool_name,
                    "call_id": request.call_id,
                    "status": finished.status,
                    "error_type": finished.error_type,
                },
            )
        return finished

    def _emit(
        self,
        kind: str,
        message: str,
        payload: dict[str, Any],
    ) -> None:
        if self.event_sink is None:
            return
        try:
            event_payload = {"run_id": payload.get("task_id")}
            event_payload.update(payload)
            self.event_sink(kind, message, event_payload)
        except Exception:
            return

    def _resolve(self, tool_name: str) -> tuple[ToolDescriptor | None, ToolProvider | None]:
        if tool_name == "tool_search":
            return _tool_search_descriptor(), None
        for provider in self.providers:
            descriptor = provider.get_tool(tool_name)
            if descriptor is not None:
                return descriptor, provider
        return None, None

    def _invoke_tool_search(
        self,
        request: ToolInvocationRequest,
        descriptor: ToolDescriptor,
        started_at: str,
    ) -> ToolInvocationResult:
        query = str(request.arguments.get("query") or "")
        limit_arg = request.arguments.get("limit")
        limit = limit_arg if isinstance(limit_arg, int) else 5
        matches = self.search_tools(
            query,
            context={"task_id": request.task_id},
            limit=max(1, min(limit, 10)),
        )
        loaded = [
            _compact_descriptor(tool)
            for tool in matches
        ]
        for tool in matches:
            self._emit(
                "lazy_tool_loaded",
                "Lazy tool descriptor loaded",
                {
                    "task_id": request.task_id,
                    "tool_name": tool.tool_id,
                    "provider": tool.provider,
                },
            )
        return ToolInvocationResult(
            task_id=request.task_id,
            tool_name=request.tool_name,
            call_id=request.call_id,
            provider_type=descriptor.provider_type,
            decision="allowed",
            status="success",
            output={
                "query": query,
                "purpose": request.arguments.get("purpose"),
                "matches": loaded,
            },
            started_at=started_at,
        )

    def _create_approval_request(
        self,
        request: ToolInvocationRequest,
        descriptor: ToolDescriptor,
        risk_check: RiskCheckResult | None,
        reason: str | None,
    ) -> str:
        existing = self._find_existing_pending(request)
        if existing is not None:
            return existing.approval_id

        approval = self.approval_store.create_request(
            task_id=request.task_id,
            reason=reason or f"Tool requires approval: {request.tool_name}",
            risk_level="sensitive",
            tool_name=request.tool_name,
            action_type=_action_detail(request.arguments, "action_type"),
            target_hint=_action_detail(request.arguments, "target_hint"),
            metadata={
                "workflow": request.workflow_backend,
                "risk_check": risk_check.model_dump(mode="json")
                if risk_check is not None
                else None,
                "tool_descriptor": descriptor.model_dump(mode="json"),
            },
        )
        if risk_check is not None:
            risk_check = risk_check.model_copy(
                update={"approval_request_id": approval.approval_id}
            )
            self.approval_store.record_check(request.task_id, risk_check)
        self.pending_manager.create_pending_tool_call(
            task_id=request.task_id,
            approval_id=approval.approval_id,
            tool_name=request.tool_name,
            arguments=request.arguments,
            tool_call_id=request.call_id,
            reason=reason or "Approval required before tool execution.",
            metadata={
                "workflow": request.workflow_backend,
                "context_snapshot": request.context_snapshot,
                "page_observation": request.page_observation,
                "call": {
                    "call_id": request.call_id,
                    "tool_id": request.tool_name,
                    "arguments": request.arguments,
                },
                "risk_check": risk_check.model_dump(mode="json")
                if risk_check is not None
                else None,
            },
        )
        self._write_approval_artifacts(request)
        return approval.approval_id

    def _find_existing_pending(self, request: ToolInvocationRequest):
        for pending in self.pending_manager.list_for_task(request.task_id):
            if pending.tool_name == request.tool_name and pending.arguments == request.arguments:
                return pending
        return None

    def _write_approval_artifacts(self, request: ToolInvocationRequest) -> None:
        if request.run_dir is None:
            return
        run_dir = Path(request.run_dir)
        try:
            self.approval_store.write_jsonl_for_task(
                request.task_id,
                run_dir / "approvals.jsonl",
            )
            self.approval_store.write_risk_report(
                request.task_id,
                run_dir / "risk_report.json",
            )
            self.pending_manager.write_jsonl(request.task_id, run_dir / "pending.jsonl")
        except Exception:
            return

    def _finish(
        self,
        request: ToolInvocationRequest,
        descriptor: ToolDescriptor | None,
        result: ToolInvocationResult,
        started: float,
        risk_check: RiskCheckResult | None,
    ) -> ToolInvocationResult:
        duration_ms = round((perf_counter() - started) * 1000, 4)
        result.ended_at = result.ended_at or utc_now()
        result.duration_ms = duration_ms
        if risk_check is not None:
            result.metadata["risk_check"] = risk_check.model_dump(mode="json")
            if result.status != "approval_required":
                self.approval_store.record_check(request.task_id, risk_check)
                self._write_approval_artifacts(request)
        if result.error_message:
            result.metadata.setdefault("error_message", result.error_message)
        self.audit_store.append(
            ToolAuditEvent(
                timestamp=result.ended_at,
                task_id=request.task_id,
                workflow_backend=request.workflow_backend,
                tool_name=request.tool_name,
                provider_type=descriptor.provider_type if descriptor else None,
                permission=descriptor.permission if descriptor else None,
                risk_level=descriptor.risk_level if descriptor else None,
                decision=result.decision,
                status=result.status,
                error_type=result.error_type,
                error_message=result.error_message,
                duration_ms=duration_ms,
                approval_id=result.approval_id,
                metadata=result.metadata,
            )
        )
        return result


def _action_detail(arguments: dict[str, Any], key: str) -> str | None:
    action = arguments.get("action")
    if not isinstance(action, dict):
        return None
    value = action.get(key)
    return str(value) if value is not None else None


def _tool_search_descriptor() -> ToolDescriptor:
    return ToolDescriptor(
        tool_id="tool_search",
        name="Tool Search",
        description="Search compact lazy tool metadata before loading or using a lazy tool.",
        provider_type="local",
        loading_mode="core",
        provider="gateway",
        input_schema={
            "schema": {
                "query": "string",
                "purpose": "string optional",
                "limit": "integer optional",
            }
        },
        output_schema={"schema": {"matches": "array of compact lazy descriptors"}},
        schema_summary={"query": "string", "purpose": "string optional"},
        tags=["tool", "search", "lazy", "discovery"],
    )


def _searchable_lazy_tool(tool: ToolDescriptor) -> bool:
    return (
        tool.loading_mode == "lazy"
        and tool.exposure == "lazy"
        and tool.enabled
        and not tool.compatibility_wrapper
    )


def _loadable_tool(tool: ToolDescriptor) -> bool:
    return tool.enabled and tool.exposure not in {"hidden", "disabled", "compatibility"}


def _compact_descriptor(tool: ToolDescriptor) -> dict[str, Any]:
    return {
        "id": tool.tool_id,
        "description": tool.description,
        "loading_mode": tool.loading_mode,
        "exposure": tool.exposure,
        "provider": tool.provider,
        "risk_level": tool.risk_level,
        "required_context": tool.required_context,
        "schema_summary": tool.schema_summary or tool.input_schema.schema,
    }


def _context_task_id(context: dict[str, Any] | None) -> str | None:
    if not isinstance(context, dict):
        return None
    value = context.get("task_id") or context.get("run_id")
    return str(value) if value else None
