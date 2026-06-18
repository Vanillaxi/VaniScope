from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from webscoper.runtime.safety.risk_gate import RiskGate
from webscoper.schemas.risk import RiskCheckResult
from webscoper.tools.gateway.descriptors import ToolDescriptor


@dataclass
class ToolGatewayPolicyDecision:
    decision: str
    status: str
    error_type: str | None = None
    error_message: str | None = None
    risk_check: RiskCheckResult | None = None


class ToolGatewayPolicy:
    def __init__(self, risk_gate: RiskGate | None = None) -> None:
        self.risk_gate = risk_gate or RiskGate()

    def check(
        self,
        *,
        descriptor: ToolDescriptor | None,
        task_id: str,
        tool_name: str,
        arguments: dict[str, Any],
        page_observation: Any | None = None,
        approval_override_id: str | None = None,
    ) -> ToolGatewayPolicyDecision:
        if descriptor is None:
            return ToolGatewayPolicyDecision(
                decision="blocked",
                status="blocked",
                error_type="UNKNOWN_TOOL",
                error_message=f"Unknown tool: {tool_name}",
            )
        if not descriptor.enabled:
            return ToolGatewayPolicyDecision(
                decision="blocked",
                status="blocked",
                error_type="TOOL_DISABLED",
                error_message=f"Tool is disabled: {tool_name}",
            )
        if descriptor.risk_level == "dangerous" or descriptor.permission == "dangerous":
            return ToolGatewayPolicyDecision(
                decision="blocked",
                status="blocked",
                error_type="TOOL_DANGEROUS",
                error_message=f"Tool is dangerous and blocked: {tool_name}",
            )

        should_risk_check = (
            tool_name == "browser_click_intent"
            or descriptor.permission != "read_only"
            or descriptor.risk_level != "read_only"
        )

        if approval_override_id is None and should_risk_check:
            risk = self.risk_gate.check_tool_call(
                task_id=task_id,
                tool_name=tool_name,
                arguments=arguments,
                page_observation=page_observation,
            )
            if risk.blocked:
                return ToolGatewayPolicyDecision(
                    decision="blocked",
                    status="blocked",
                    error_type="RISK_BLOCKED",
                    error_message=risk.reason,
                    risk_check=risk,
                )
            if risk.requires_approval:
                return ToolGatewayPolicyDecision(
                    decision="approval_required",
                    status="approval_required",
                    error_type="RISK_APPROVAL_REQUIRED",
                    error_message=risk.reason,
                    risk_check=risk,
                )

        if descriptor.risk_level == "sensitive" or descriptor.permission == "sensitive":
            return ToolGatewayPolicyDecision(
                decision="approval_required",
                status="approval_required",
                error_type="TOOL_APPROVAL_REQUIRED",
                error_message=f"Tool requires approval: {tool_name}",
            )

        return ToolGatewayPolicyDecision(decision="allowed", status="success")
