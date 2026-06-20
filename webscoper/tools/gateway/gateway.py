from __future__ import annotations

from pathlib import Path
from time import perf_counter
from typing import Any

from webscoper.runtime.execution.events import TaskEventSink
from webscoper.runtime.safety.approvals import ApprovalStore
from webscoper.runtime.safety.pending import PendingApprovalManager
from webscoper.schemas.runtime import RiskCheckResult
from webscoper.tools.gateway.audit import ToolAuditEvent, ToolGatewayAuditStore, utc_now
from webscoper.tools.gateway.descriptors import (
    ToolDescriptor,
    ToolInvocationRequest,
    ToolInvocationResult,
)
from webscoper.tools.gateway.policy import ToolGatewayPolicy
from webscoper.tools.gateway.providers import ToolProvider


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
        tools: list[ToolDescriptor] = []
        for provider in self.providers:
            tools.extend(provider.list_tools())
        return tools

    def search_tools(self, query: str) -> list[ToolDescriptor]:
        normalized = query.lower().strip()
        if not normalized:
            return []
        matches: list[ToolDescriptor] = []
        for tool in self.list_tools():
            haystack = " ".join(
                [tool.tool_id, tool.name, tool.description, " ".join(tool.tags)]
            ).lower()
            if normalized in haystack or all(term in haystack for term in normalized.split()):
                matches.append(tool)
        return matches

    def get_tool(self, tool_name: str) -> ToolDescriptor:
        descriptor, _provider = self._resolve(tool_name)
        if descriptor is None:
            raise KeyError(f"Unknown tool: {tool_name}")
        return descriptor

    def get_tool_schema(self, tool_name: str) -> dict[str, Any]:
        return self.get_tool(tool_name).model_dump(mode="json")

    async def invoke(self, request: ToolInvocationRequest) -> ToolInvocationResult:
        started = perf_counter()
        started_at = utc_now()
        descriptor, provider = self._resolve(request.tool_name)
        policy_decision = self.policy.check(
            descriptor=descriptor,
            task_id=request.task_id,
            tool_name=request.tool_name,
            arguments=request.arguments,
            page_observation=request.page_observation,
            approval_override_id=request.approval_override_id,
        )

        if policy_decision.decision == "blocked" or descriptor is None or provider is None:
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
        return self._finish(request, descriptor, result, started, policy_decision.risk_check)

    def _resolve(self, tool_name: str) -> tuple[ToolDescriptor | None, ToolProvider | None]:
        for provider in self.providers:
            descriptor = provider.get_tool(tool_name)
            if descriptor is not None:
                return descriptor, provider
        return None, None

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
