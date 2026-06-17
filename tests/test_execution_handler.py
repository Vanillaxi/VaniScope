from __future__ import annotations

import json
from pathlib import Path

import pytest

from webscoper.runtime.execution import WebAgentExecutionHandler
from webscoper.schemas.action import ActionContract, ExpectedEffect
from webscoper.schemas.observation import PageObservation
from webscoper.schemas.task import TaskSpec


@pytest.mark.asyncio
async def test_execution_handler_open_only_lifecycle(tmp_path: Path) -> None:
    task = TaskSpec(
        task_id="open_basic",
        raw_input="Open local basic mock.",
        target_url=Path("tests/fixtures/mock_site/basic.html").resolve().as_uri(),
        action=None,
        tags=["test", "open"],
    )
    handler = WebAgentExecutionHandler(output_root=tmp_path)

    observation = await handler.run(task)

    assert isinstance(observation, PageObservation)
    context = handler.last_context
    assert context is not None
    assert context.trace_recorder.trace_path.exists()
    assert context.transcript_store.transcript_path.exists()

    event_types = _event_types(context.transcript_store.transcript_path)
    assert "task_loaded" in event_types
    assert "context_built" in event_types
    assert "execution_started" in event_types
    assert "execution_completed" in event_types


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
