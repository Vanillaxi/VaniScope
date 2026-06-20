from __future__ import annotations

from webscoper.tools.gateway import ToolDescriptor, ToolGatewayPolicy


def test_tool_gateway_policy_core_decisions() -> None:
    policy = ToolGatewayPolicy()
    cases = [
        (
            ToolDescriptor(
                tool_id="local_echo",
                name="Local Echo",
                description="Echo text.",
                provider_type="local",
            ),
            "local_echo",
            "allowed",
            None,
        ),
        (
            ToolDescriptor(
                tool_id="sensitive_tool",
                name="Sensitive Tool",
                description="Sensitive tool.",
                provider_type="local",
                risk_level="sensitive",
                permission="sensitive",
            ),
            "sensitive_tool",
            "approval_required",
            None,
        ),
        (
            ToolDescriptor(
                tool_id="dangerous_tool",
                name="Dangerous Tool",
                description="Dangerous tool.",
                provider_type="local",
                risk_level="dangerous",
                permission="dangerous",
            ),
            "dangerous_tool",
            "blocked",
            None,
        ),
        (
            ToolDescriptor(
                tool_id="disabled_tool",
                name="Disabled Tool",
                description="Disabled tool.",
                provider_type="local",
                enabled=False,
            ),
            "disabled_tool",
            "blocked",
            "TOOL_DISABLED",
        ),
        (None, "missing_tool", "blocked", "UNKNOWN_TOOL"),
    ]

    for descriptor, tool_name, decision_type, error_type in cases:
        decision = policy.check(
            descriptor=descriptor,
            task_id="task",
            tool_name=tool_name,
            arguments={},
        )
        assert decision.decision == decision_type
        if error_type is not None:
            assert decision.error_type == error_type
