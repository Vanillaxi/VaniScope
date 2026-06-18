from __future__ import annotations

import json
from pathlib import Path

from webscoper.tools.gateway.audit import ToolAuditEvent, ToolGatewayAuditStore


def test_tool_gateway_audit_store_writes_jsonl(tmp_path: Path) -> None:
    path = tmp_path / "tool_audit.jsonl"
    store = ToolGatewayAuditStore(path)

    store.append(
        ToolAuditEvent(
            timestamp="2026-01-01T00:00:00+00:00",
            task_id="task",
            workflow_backend="langgraph",
            tool_name="fake_mcp_echo",
            provider_type="mcp",
            permission="read_only",
            risk_level="read_only",
            decision="allowed",
            status="success",
            duration_ms=1.0,
        )
    )

    payload = json.loads(path.read_text(encoding="utf-8").strip())
    assert payload["tool_name"] == "fake_mcp_echo"
    assert payload["workflow_backend"] == "langgraph"
