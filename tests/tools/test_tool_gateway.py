from __future__ import annotations

import json
from pathlib import Path

import pytest

from webscoper.runtime.safety.approvals import ApprovalStore
from webscoper.runtime.safety.approvals import PendingApprovalManager
from webscoper.tools.gateway import (
    FakeMCPToolProvider,
    LocalToolProvider,
    ToolDescriptor,
    ToolGateway,
    ToolGatewayAuditStore,
    ToolInvocationRequest,
)


@pytest.mark.asyncio
async def test_tool_gateway_registers_providers_and_searches_tools(tmp_path: Path) -> None:
    gateway = _gateway(tmp_path)

    tools = gateway.list_tools()
    matches = gateway.search_tools("mcp echo")

    assert {tool.provider_type for tool in tools} >= {"local", "mcp"}
    assert any(tool.tool_id == "fake_mcp_echo" for tool in matches)
    assert gateway.get_tool_schema("fake_mcp_echo")["tool_id"] == "fake_mcp_echo"


@pytest.mark.asyncio
async def test_tool_gateway_invokes_local_and_fake_mcp_tools(tmp_path: Path) -> None:
    gateway = _gateway(tmp_path)

    local = await gateway.invoke(
        ToolInvocationRequest(
            task_id="task",
            tool_name="local_echo",
            arguments={"text": "local"},
            run_dir=str(tmp_path),
        )
    )
    fake = await gateway.invoke(
        ToolInvocationRequest(
            task_id="task",
            tool_name="fake_mcp_echo",
            arguments={"text": "mcp"},
            run_dir=str(tmp_path),
        )
    )

    assert local.status == "success"
    assert local.output == {"echo": "local"}
    assert fake.provider_type == "mcp"
    assert fake.output == {"text": "mcp"}


@pytest.mark.asyncio
async def test_tool_gateway_unknown_disabled_and_dangerous_tools_are_blocked(
    tmp_path: Path,
) -> None:
    gateway = _gateway(
        tmp_path,
        local_tools=[
            ToolDescriptor(
                tool_id="disabled_tool",
                name="Disabled Tool",
                description="Disabled.",
                provider_type="local",
                enabled=False,
            ),
            ToolDescriptor(
                tool_id="dangerous_tool",
                name="Dangerous Tool",
                description="Dangerous.",
                provider_type="local",
                permission="dangerous",
                risk_level="dangerous",
            ),
        ],
    )

    unknown = await gateway.invoke(
        ToolInvocationRequest(task_id="task", tool_name="missing_tool", run_dir=str(tmp_path))
    )
    disabled = await gateway.invoke(
        ToolInvocationRequest(task_id="task", tool_name="disabled_tool", run_dir=str(tmp_path))
    )
    dangerous = await gateway.invoke(
        ToolInvocationRequest(task_id="task", tool_name="dangerous_tool", run_dir=str(tmp_path))
    )

    assert unknown.error_type == "UNKNOWN_TOOL"
    assert disabled.error_type == "TOOL_DISABLED"
    assert dangerous.error_type == "TOOL_DANGEROUS"


@pytest.mark.asyncio
async def test_tool_gateway_sensitive_tool_creates_pending_approval_and_audit(
    tmp_path: Path,
) -> None:
    approval_store = ApprovalStore()
    pending_manager = PendingApprovalManager()
    gateway = _gateway(
        tmp_path,
        approval_store=approval_store,
        pending_manager=pending_manager,
        local_tools=[
            ToolDescriptor(
                tool_id="sensitive_tool",
                name="Sensitive Tool",
                description="Sensitive.",
                provider_type="local",
                permission="sensitive",
                risk_level="sensitive",
            )
        ],
    )

    result = await gateway.invoke(
        ToolInvocationRequest(
            task_id="task",
            tool_name="sensitive_tool",
            arguments={"value": "safe-test-value"},
            run_dir=str(tmp_path),
        )
    )

    assert result.status == "approval_required"
    assert approval_store.list_for_task("task")[0].status == "pending"
    assert pending_manager.list_for_task("task")[0].tool_name == "sensitive_tool"
    audit = [
        json.loads(line)
        for line in (tmp_path / "tool_audit.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert audit[-1]["decision"] == "approval_required"


def _gateway(
    tmp_path: Path,
    *,
    local_tools: list[ToolDescriptor] | None = None,
    approval_store: ApprovalStore | None = None,
    pending_manager: PendingApprovalManager | None = None,
) -> ToolGateway:
    return ToolGateway(
        providers=[
            LocalToolProvider(tools=local_tools),
            FakeMCPToolProvider(),
        ],
        audit_store=ToolGatewayAuditStore(tmp_path / "tool_audit.jsonl"),
        approval_store=approval_store or ApprovalStore(),
        pending_manager=pending_manager or PendingApprovalManager(),
    )
