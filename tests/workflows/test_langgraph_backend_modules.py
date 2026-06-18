from __future__ import annotations

from pathlib import Path

from webscoper.runtime.execution.handler import WebAgentExecutionHandler
from webscoper.runtime.task_runner import build_task_spec


def test_langgraph_adapter_imports_remain_compatible() -> None:
    from webscoper.workflows.langgraph_adapter import (
        LangGraphWorkflowAdapter as LegacyAdapter,
    )
    from webscoper.workflows.langgraph_backend.adapter import (
        LangGraphWorkflowAdapter as BackendAdapter,
    )

    assert LegacyAdapter is BackendAdapter


def test_langgraph_workflow_events_still_emit(tmp_path: Path) -> None:
    from webscoper.workflows.langgraph_backend.adapter import LangGraphWorkflowAdapter

    events: list[str] = []
    handler = WebAgentExecutionHandler(
        output_root=tmp_path,
        workspace=Path("tests/fixtures/workspace"),
        event_sink=lambda kind, _message, _payload: events.append(kind),
    )
    task = build_task_spec(
        url="tests/fixtures/mock_site/basic.html",
        click="Quickstart",
        expect="pip install playwright",
    )

    result = LangGraphWorkflowAdapter(handler).run(task)

    assert result.status == "succeeded"
    assert "workflow_started" in events
    assert "workflow_finished" in events
