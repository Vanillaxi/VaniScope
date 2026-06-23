from __future__ import annotations

import json
from pathlib import Path

import pytest

from webscoper.browser.public_web import PublicWebRuntimeConfig
from webscoper.runtime.safety.approvals import ApprovalStore
from webscoper.runtime.safety.approvals import PendingApprovalManager
from webscoper.tools.gateway import (
    LocalToolProvider,
    ResearchToolProvider,
    ToolDescriptor,
    ToolGateway,
    ToolGatewayAuditStore,
    ToolInvocationRequest,
)
from webscoper.tools.registry import create_default_tool_registry


@pytest.mark.asyncio
async def test_tool_gateway_search_loads_and_executes_research_lazy_tool(
    tmp_path: Path,
) -> None:
    events: list[str] = []
    gateway = _gateway(
        tmp_path,
        event_sink=lambda kind, _message, _payload: events.append(kind),
    )

    search = await gateway.invoke(
        ToolInvocationRequest(
            task_id="task",
            tool_name="tool_search",
            arguments={"query": "github issue", "purpose": "research issue"},
            run_dir=str(tmp_path),
        )
    )
    match_ids = [match["id"] for match in search.output["matches"]]
    load = await gateway.invoke(
        ToolInvocationRequest(
            task_id="task",
            tool_name="tool_load",
            arguments={"tool_id": "github_fetch_issue"},
            run_dir=str(tmp_path),
        )
    )
    html = Path("tests/fixtures/mock_site/github_issue_research.html").read_text(
        encoding="utf-8"
    )
    issue = await gateway.invoke(
        ToolInvocationRequest(
            task_id="task",
            tool_name="github_fetch_issue",
            arguments={
                "url": "https://github.com/apache/dubbo-go/issues/4821",
                "html": html,
            },
            run_dir=str(tmp_path),
        )
    )

    assert "github_fetch_issue" in match_ids
    assert load.status == "success"
    assert load.output["loaded_tool_id"] == "github_fetch_issue"
    assert load.output["loaded_tool"]["tool_id"] == "github_fetch_issue"
    assert issue.status == "success"
    assert issue.output["title"]
    assert "common/url.go" in issue.output["body_text"]
    assert "lazy_tool_search_started" in events
    assert "lazy_tool_search_finished" in events
    assert "lazy_tool_load_started" in events
    assert "lazy_tool_load_finished" in events
    assert "lazy_tool_loaded" in events
    assert "lazy_tool_execution_started" in events
    assert "lazy_tool_execution_finished" in events


@pytest.mark.asyncio
async def test_tool_gateway_invokes_local_and_docs_table_research_tools(
    tmp_path: Path,
) -> None:
    gateway = _gateway(tmp_path)
    docs_html = Path("tests/fixtures/mock_site/docs_research.html").read_text(
        encoding="utf-8"
    )

    local = await gateway.invoke(
        ToolInvocationRequest(
            task_id="task",
            tool_name="local_echo",
            arguments={"text": "local"},
            run_dir=str(tmp_path),
        )
    )
    docs = await gateway.invoke(
        ToolInvocationRequest(
            task_id="task",
            tool_name="docs_extract",
            arguments={"html": docs_html, "query": "install"},
            run_dir=str(tmp_path),
        )
    )
    table = await gateway.invoke(
        ToolInvocationRequest(
            task_id="task",
            tool_name="table_extract",
            arguments={"html": "<table><tr><th>Name</th></tr><tr><td>VaniScope</td></tr></table>"},
            run_dir=str(tmp_path),
        )
    )

    assert local.status == "success"
    assert local.output == {"echo": "local"}
    assert docs.status == "success"
    assert "uv sync" in docs.output["content_text"]
    assert table.status == "success"
    assert table.output["tables"][0]["rows"][0]["Name"] == "VaniScope"


@pytest.mark.asyncio
async def test_tool_gateway_unknown_disabled_compatibility_and_dangerous_tools_are_blocked(
    tmp_path: Path,
) -> None:
    gateway = _gateway(
        tmp_path,
        local_tools=[
            ToolDescriptor(
                tool_id="compat_tool",
                name="Compat Tool",
                description="Compatibility.",
                provider_type="local",
                compatibility_wrapper=True,
                exposure="compatibility",
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
        ToolInvocationRequest(task_id="task", tool_name="web_search", run_dir=str(tmp_path))
    )
    compatibility = await gateway.invoke(
        ToolInvocationRequest(task_id="task", tool_name="compat_tool", run_dir=str(tmp_path))
    )
    dangerous = await gateway.invoke(
        ToolInvocationRequest(task_id="task", tool_name="dangerous_tool", run_dir=str(tmp_path))
    )

    assert unknown.error_type == "UNKNOWN_TOOL"
    assert disabled.error_type == "TOOL_DISABLED"
    assert compatibility.error_type == "TOOL_COMPATIBILITY_WRAPPER_REJECTED"
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
    event_sink=None,
) -> ToolGateway:
    registry = create_default_tool_registry()
    return ToolGateway(
        providers=[
            LocalToolProvider(tools=local_tools),
            ResearchToolProvider(
                tool_registry=registry,
                public_web_config=PublicWebRuntimeConfig(
                    mode="public_safe",
                    public_network_enabled=True,
                    allowed_domains=["github.com"],
                ),
            ),
        ],
        audit_store=ToolGatewayAuditStore(tmp_path / "tool_audit.jsonl"),
        approval_store=approval_store or ApprovalStore(),
        pending_manager=pending_manager or PendingApprovalManager(),
        event_sink=event_sink,
    )
