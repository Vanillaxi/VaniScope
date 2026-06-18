from __future__ import annotations

import json
from pathlib import Path

from webscoper.runtime.execution.handler import WebAgentExecutionHandler
from webscoper.runtime.task_runner import build_task_spec
from webscoper.workflows.langgraph_adapter import LangGraphWorkflowAdapter


def test_langgraph_tool_node_writes_gateway_audit(tmp_path: Path) -> None:
    handler = WebAgentExecutionHandler(
        output_root=tmp_path,
        workspace=Path("tests/fixtures/workspace"),
    )
    task = build_task_spec(
        url="tests/fixtures/mock_site/basic.html",
        click="Quickstart",
        expect="pip install playwright",
    )

    result = LangGraphWorkflowAdapter(handler).run(task)

    audit_path = Path(result.run_dir or "") / "tool_audit.jsonl"
    rows = [
        json.loads(line)
        for line in audit_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert result.status == "succeeded"
    assert audit_path.exists()
    assert {row["tool_name"] for row in rows} >= {
        "browser_open_observe",
        "browser_click_intent",
        "browser_extract",
        "finish_task",
    }
    assert all(row["workflow_backend"] == "langgraph" for row in rows)
    assert all(row["provider_type"] == "browser" for row in rows)
