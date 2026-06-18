from __future__ import annotations

from pathlib import Path

from webscoper.api.schemas import TaskCreateRequest
from webscoper.runtime.task_runner import run_browser_task_sync


def test_task_create_request_defaults_to_native_workflow() -> None:
    request = TaskCreateRequest(url="tests/fixtures/mock_site/basic.html")

    assert request.workflow == "native"


def test_run_browser_task_native_workflow_regression(tmp_path: Path) -> None:
    result = run_browser_task_sync(
        url="tests/fixtures/mock_site/basic.html",
        click="Quickstart",
        expect="pip install playwright",
        planner="deterministic",
        workflow="native",
        workspace=Path("tests/fixtures/workspace"),
        reminders=["This is a test runtime reminder."],
        output_root=tmp_path,
    )

    context = result.handler.last_context
    assert context is not None
    assert context.state.status == "completed"
    assert (context.run_dir / "final_report.md").exists()
    assert not (context.run_dir / "workflow_state.json").exists()
