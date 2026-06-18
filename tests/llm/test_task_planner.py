from __future__ import annotations

from pathlib import Path

import pytest

from webscoper.runtime.context import WebAgentContext
from webscoper.runtime.llm.client import FakeLLMClient
from webscoper.runtime.llm.planner import LLMTaskPlanner
from webscoper.runtime.execution.tool_call_parser import ToolCallParser
from webscoper.runtime.artifacts.trace import TraceRecorder
from webscoper.runtime.artifacts.transcript import TranscriptStore
from webscoper.schemas.action import ActionContract, ExpectedEffect
from webscoper.schemas.context import RuntimeState
from webscoper.schemas.prompt import PromptBuildResult
from webscoper.schemas.task import TaskSpec
from webscoper.schemas.version import VersionContext


@pytest.mark.asyncio
async def test_llm_task_planner_builds_plan_from_fake_llm(tmp_path: Path) -> None:
    task = TaskSpec(
        task_id="llm_plan_click",
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
        run_id="llm_plan_click",
        run_dir=tmp_path,
        trace_recorder=TraceRecorder(run_dir=tmp_path, run_id="llm_plan_click"),
        transcript_store=TranscriptStore(run_dir=tmp_path, run_id="llm_plan_click"),
        version=VersionContext(),
        state=RuntimeState(status="running"),
    )
    planner = LLMTaskPlanner(FakeLLMClient(), ToolCallParser())

    plan = await planner.build_plan(
        context.snapshot(),
        PromptBuildResult(prompt_text="You are a browser agent."),
    )

    tool_ids = [step.tool_call.tool_id for step in plan.steps]
    assert plan.plan_id.startswith("llm_plan_")
    assert "browser_open_observe" in tool_ids
    assert "browser_click_intent" in tool_ids
    assert "finish_task" in tool_ids
