from __future__ import annotations

from webscoper.tools.gateway import ToolDescriptor, ToolGatewayPolicy


def test_tool_gateway_policy_allows_read_only_tool() -> None:
    decision = ToolGatewayPolicy().check(
        descriptor=ToolDescriptor(
            tool_id="local_echo",
            name="Local Echo",
            description="Echo text.",
            provider_type="local",
        ),
        task_id="task",
        tool_name="local_echo",
        arguments={},
    )

    assert decision.decision == "allowed"


def test_tool_gateway_policy_requires_approval_for_sensitive_tool() -> None:
    decision = ToolGatewayPolicy().check(
        descriptor=ToolDescriptor(
            tool_id="sensitive_tool",
            name="Sensitive Tool",
            description="Sensitive tool.",
            provider_type="local",
            risk_level="sensitive",
            permission="sensitive",
        ),
        task_id="task",
        tool_name="sensitive_tool",
        arguments={},
    )

    assert decision.decision == "approval_required"


def test_tool_gateway_policy_blocks_dangerous_disabled_and_unknown_tools() -> None:
    policy = ToolGatewayPolicy()

    dangerous = policy.check(
        descriptor=ToolDescriptor(
            tool_id="dangerous_tool",
            name="Dangerous Tool",
            description="Dangerous tool.",
            provider_type="local",
            risk_level="dangerous",
            permission="dangerous",
        ),
        task_id="task",
        tool_name="dangerous_tool",
        arguments={},
    )
    disabled = policy.check(
        descriptor=ToolDescriptor(
            tool_id="disabled_tool",
            name="Disabled Tool",
            description="Disabled tool.",
            provider_type="local",
            enabled=False,
        ),
        task_id="task",
        tool_name="disabled_tool",
        arguments={},
    )
    unknown = policy.check(
        descriptor=None,
        task_id="task",
        tool_name="missing_tool",
        arguments={},
    )

    assert dangerous.decision == "blocked"
    assert disabled.error_type == "TOOL_DISABLED"
    assert unknown.error_type == "UNKNOWN_TOOL"
