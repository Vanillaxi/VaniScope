from __future__ import annotations

from pathlib import Path

from webscoper.api.schemas import TaskCreateRequest
from webscoper.runtime.execution.runner import run_browser_task_sync


def test_task_create_request_defaults_to_langgraph_workflow() -> None:
    request = TaskCreateRequest(url="tests/fixtures/mock_site/basic.html")

    assert request.workflow == "langgraph"


def test_run_browser_task_uses_langgraph_workflow(tmp_path: Path) -> None:
    result = run_browser_task_sync(
        url="tests/fixtures/mock_site/basic.html",
        click="Quickstart",
        expect="pip install playwright",
        planner="deterministic",
        workspace=Path("tests/fixtures/workspace"),
        reminders=["This is a test runtime reminder."],
        output_root=tmp_path,
    )

    context = result.handler.last_context
    assert context is not None
    assert context.state.status == "completed"
    assert (context.run_dir / "final_report.md").exists()
    assert (context.run_dir / "workflow_state.json").exists()
