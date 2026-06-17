from __future__ import annotations

import json
from pathlib import Path

import pytest

from webscoper.runtime.execution import WebAgentExecutionHandler
from webscoper.schemas.action import ActionContract, ExpectedEffect
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
