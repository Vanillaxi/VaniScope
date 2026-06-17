from __future__ import annotations

import json
import builtins
from pathlib import Path

from webscoper.runtime.task_runner import run_browser_task_sync


def test_langgraph_workflow_generates_core_artifacts(tmp_path: Path) -> None:
    result = run_browser_task_sync(
        url="tests/fixtures/mock_site/basic.html",
        click="Quickstart",
        expect="pip install playwright",
        planner="deterministic",
        workflow="langgraph",
        workspace=Path("tests/fixtures/workspace"),
        reminders=["This is a test runtime reminder."],
        output_root=tmp_path,
    )

    context = result.handler.last_context
    assert context is not None
    run_dir = context.run_dir
    assert context.state.status == "completed"
    assert (run_dir / "final_report.md").exists()
    assert (run_dir / "review.json").exists()
    assert (run_dir / "compact_context.json").exists()
    assert (run_dir / "workflow_state.json").exists()

    workflow_state = json.loads((run_dir / "workflow_state.json").read_text())
    assert workflow_state["status"] == "succeeded"
    assert workflow_state["metadata"]["backend"] == "langgraph"
    assert "final_report.md" in workflow_state["artifacts"]


def test_langgraph_fake_llm_planner_runs(tmp_path: Path) -> None:
    result = run_browser_task_sync(
        url="tests/fixtures/mock_site/basic.html",
        click="Quickstart",
        expect="pip install playwright",
        planner="fake_llm",
        workflow="langgraph",
        workspace=Path("tests/fixtures/workspace"),
        reminders=["Return valid JSON tool_calls only."],
        output_root=tmp_path,
    )

    context = result.handler.last_context
    assert context is not None
    assert context.state.status == "completed"
    assert (context.run_dir / "workflow_state.json").exists()


def test_langgraph_fake_llm_revise_loop_runs(tmp_path: Path) -> None:
    result = run_browser_task_sync(
        url="tests/fixtures/mock_site/basic.html",
        click="Quickstart",
        expect="pip install playwright",
        planner="deterministic",
        workflow="langgraph",
        reviewer="fake_llm",
        revise_attempts=1,
        workspace=Path("tests/fixtures/workspace"),
        reminders=["Review and revise report against evidence."],
        output_root=tmp_path,
    )

    context = result.handler.last_context
    assert context is not None
    assert (context.run_dir / "revised_report.md").exists()
    assert (context.run_dir / "final_review.json").exists()
    assert (context.run_dir / "revise_loop.json").exists()


def test_langgraph_missing_dependency_error(monkeypatch, tmp_path: Path) -> None:
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "langgraph.graph":
            raise ImportError("No module named langgraph")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    try:
        run_browser_task_sync(
            url="tests/fixtures/mock_site/basic.html",
            click="Quickstart",
            expect="pip install playwright",
            workflow="langgraph",
            output_root=tmp_path,
        )
    except RuntimeError as exc:
        assert "LangGraph workflow requested but langgraph is not installed" in str(exc)
    else:
        raise AssertionError("Expected missing LangGraph dependency error.")
