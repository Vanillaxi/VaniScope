from __future__ import annotations

# From test_deterministic_planner.py
from webscoper.runtime.execution.planner import DeterministicTaskPlanner
from webscoper.schemas.browser import ActionContract, ExpectedEffect
from webscoper.schemas.task import TaskSpec


def test_deterministic_planner_builds_open_and_click_plans() -> None:
    open_task = TaskSpec(
        task_id="open_task",
        raw_input="Open a page.",
        target_url="file:///tmp/basic.html",
    )
    action = ActionContract(
        action_type="click",
        intent="Click Quickstart",
        target_hint="Quickstart",
        preferred_roles=["button", "link"],
        preconditions=["target_visible", "target_enabled"],
        expected_effect=ExpectedEffect(
            type="content_appears",
            value="pip install playwright",
        ),
        risk_level="read_only",
    )
    click_task = TaskSpec(
        task_id="click_task",
        raw_input="Click Quickstart.",
        target_url="file:///tmp/basic.html",
        action=action,
    )

    open_tool_ids = [
        step.tool_call.tool_id
        for step in DeterministicTaskPlanner().build_plan(open_task).steps
    ]
    click_tool_ids = [
        step.tool_call.tool_id
        for step in DeterministicTaskPlanner().build_plan(click_task).steps
    ]

    assert open_tool_ids == ["browser_open_observe", "browser_extract", "finish_task"]
    assert click_tool_ids == [
        "browser_open_observe",
        "browser_click_intent",
        "browser_extract",
        "finish_task",
    ]

# From test_execution_handler.py
import json
from pathlib import Path

import pytest

from webscoper.runtime.execution.handler import WebAgentExecutionHandler
from webscoper.schemas.browser import ActionContract, ExpectedEffect
from webscoper.schemas.browser import PageObservation
from webscoper.schemas.task import TaskSpec


@pytest.mark.asyncio
async def test_execution_handler_click_task_writes_trace_and_transcript(
    tmp_path: Path,
) -> None:
    action = ActionContract(
        action_type="click",
        intent="Click Quickstart",
        target_hint="Quickstart",
        preferred_roles=["button", "link"],
        preconditions=["target_visible", "target_enabled"],
        expected_effect=ExpectedEffect(
            type="content_appears",
            value="pip install playwright",
        ),
        risk_level="read_only",
    )
    task = TaskSpec(
        task_id="click_basic",
        raw_input="Open local basic mock and click Quickstart.",
        target_url=Path("tests/fixtures/mock_site/basic.html").resolve().as_uri(),
        action=action,
        expected_effect=action.expected_effect,
        tags=["test", "click"],
    )
    handler = WebAgentExecutionHandler(output_root=tmp_path)

    observation = await handler.run(task)

    assert "pip install playwright" in observation.visible_text_summary
    context = handler.last_context
    assert context is not None
    assert context.transcript_store.transcript_path.exists()

    trace_action_types = _trace_action_types(context.trace_recorder.trace_path)
    assert "browser_click_intent" in trace_action_types
    assert "effect_verify" in trace_action_types


def _event_types(transcript_path: Path) -> list[str]:
    return [
        json.loads(line)["event_type"]
        for line in transcript_path.read_text(encoding="utf-8").splitlines()
    ]


def _trace_action_types(trace_path: Path) -> list[str]:
    return [
        json.loads(line)["action_type"]
        for line in trace_path.read_text(encoding="utf-8").splitlines()
    ]

# From test_execution_handler_fake_llm.py
import json
from pathlib import Path

import pytest

from webscoper.runtime.execution.handler import WebAgentExecutionHandler
from webscoper.schemas.browser import ActionContract, ExpectedEffect
from webscoper.schemas.task import TaskSpec


@pytest.mark.asyncio
async def test_execution_handler_runs_fake_llm_planner_mode(tmp_path: Path) -> None:
    action = ActionContract(
        action_type="click",
        intent="Click Quickstart",
        target_hint="Quickstart",
        preferred_roles=["button", "link"],
        preconditions=["target_visible", "target_enabled"],
        expected_effect=ExpectedEffect(
            type="content_appears",
            value="pip install playwright",
        ),
        risk_level="read_only",
    )
    task = TaskSpec(
        task_id="handler_fake_llm",
        raw_input="Open local basic mock and click Quickstart.",
        target_url=Path("tests/fixtures/mock_site/basic.html").resolve().as_uri(),
        action=action,
        expected_effect=action.expected_effect,
    )
    handler = WebAgentExecutionHandler(
        output_root=tmp_path,
        planner_mode="fake_llm",
    )

    observation = await handler.run(task)

    context = handler.last_context
    assert context is not None
    assert "pip install playwright" in observation.visible_text_summary
    assert context.transcript_store.transcript_path.exists()
    assert context.trace_recorder.trace_path.exists()
    assert (context.run_dir / "prompt_preview.md").exists()
    assert (context.run_dir / "prompt_context.json").exists()

    event_types = _jsonl_values(context.transcript_store.transcript_path, "event_type")
    assert "prompt_built" in event_types
    assert "llm_request" in event_types
    assert "llm_response" in event_types
    assert "plan_built" in event_types
    assert "tool_call_completed" in event_types
    assert "execution_completed" in event_types

    trace_actions = _jsonl_values(context.trace_recorder.trace_path, "action_type")
    assert "browser_open_observe" in trace_actions
    assert "browser_click_intent" in trace_actions
    assert "effect_verify" in trace_actions
    assert "browser_extract" in trace_actions
    assert "finish_task" in trace_actions


def _jsonl_values(path: Path, key: str) -> list[str]:
    return [
        json.loads(line)[key]
        for line in path.read_text(encoding="utf-8").splitlines()
    ]

# From test_task_service.py
from pathlib import Path

import pytest

from webscoper.api.schemas import TaskCreateRequest
from webscoper.api.task_service import TaskService


def test_task_service_runs_fake_llm_task(tmp_path: Path) -> None:
    service = TaskService(runs_dir=tmp_path / "runs")

    response = service.create_and_run_task(
        TaskCreateRequest(
            url="tests/fixtures/mock_site/basic.html",
            click="Quickstart",
            expect="pip install playwright",
            planner="fake_llm",
            workspace="tests/fixtures/workspace",
            reminder="This is a test runtime reminder.",
        )
    )

    assert response.status == "succeeded"
    assert "final_report.md" in response.artifacts
    assert "review_summary.md" in response.artifacts

    status = service.get_task_status(response.task_id)
    assert status.status == "succeeded"
    assert status.run_dir == response.run_dir


def test_task_service_rejects_disallowed_artifact(tmp_path: Path) -> None:
    service = TaskService(runs_dir=tmp_path / "runs")
    run_dir = tmp_path / "runs" / "task_test"
    run_dir.mkdir(parents=True)

    with pytest.raises(ValueError, match="not allowed"):
        service.read_artifact("task_test", "../../../.env")


def test_task_service_returns_not_found_status(tmp_path: Path) -> None:
    service = TaskService(runs_dir=tmp_path / "runs")

    status = service.get_task_status("missing")

    assert status.status == "not_found"
