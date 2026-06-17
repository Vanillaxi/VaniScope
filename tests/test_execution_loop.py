from __future__ import annotations

import json
from pathlib import Path

import pytest

from webscoper.runtime.context import WebAgentContext
from webscoper.runtime.execution_loop import AgentExecutionLoop
from webscoper.runtime.planner import DeterministicTaskPlanner
from webscoper.runtime.tool_executor import LocalToolExecutor
from webscoper.runtime.trace import TraceRecorder
from webscoper.runtime.transcript import TranscriptStore
from webscoper.schemas.action import ActionContract, ExpectedEffect
from webscoper.schemas.context import RuntimeState
from webscoper.schemas.task import TaskSpec
from webscoper.schemas.version import VersionContext
from webscoper.tools.browser_tools import StatefulBrowserToolRuntime
from webscoper.tools.registry import create_default_tool_registry


@pytest.mark.asyncio
async def test_agent_execution_loop_runs_click_plan(tmp_path: Path) -> None:
    run_dir = tmp_path / "run_loop"
    recorder = TraceRecorder(run_dir=run_dir, run_id="run_loop")
    transcript = TranscriptStore(run_dir=run_dir, run_id="run_loop")
    task = TaskSpec(
        task_id="loop_click",
        raw_input="Click Quickstart.",
        target_url=Path("tests/fixtures/mock_site/basic.html").resolve().as_uri(),
        action=ActionContract(
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
        ),
    )
    context = WebAgentContext(
        task=task,
        run_id="run_loop",
        run_dir=run_dir,
        trace_recorder=recorder,
        transcript_store=transcript,
        version=VersionContext(),
        state=RuntimeState(status="running"),
    )
    browser_runtime = StatefulBrowserToolRuntime(trace_recorder=recorder)
    loop = AgentExecutionLoop(
        planner=DeterministicTaskPlanner(),
        tool_executor=LocalToolExecutor(
            tool_registry=create_default_tool_registry(),
            browser_runtime=browser_runtime,
        ),
    )

    await browser_runtime.start()
    try:
        result = await loop.run(context)
    finally:
        await browser_runtime.close()

    transcript_events = _jsonl_values(transcript.transcript_path, "event_type")
    trace_actions = _jsonl_values(recorder.trace_path, "action_type")

    assert result.status == "success"
    assert len(result.records) >= 4
    assert "plan_built" in transcript_events
    assert "tool_call_started" in transcript_events
    assert "tool_call_completed" in transcript_events
    assert "execution_loop_completed" in transcript_events
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
