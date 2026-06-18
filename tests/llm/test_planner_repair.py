from __future__ import annotations

import json
from pathlib import Path

import pytest

from webscoper.runtime.context import WebAgentContext
from webscoper.runtime.llm_client import BaseLLMClient
from webscoper.runtime.llm_planner import LLMTaskPlanner
from webscoper.runtime.trace import TraceRecorder
from webscoper.runtime.transcript import TranscriptStore
from webscoper.schemas.context import RuntimeState
from webscoper.schemas.llm import LLMRequest, LLMResponse
from webscoper.schemas.prompt import PromptBuildResult
from webscoper.schemas.task import TaskSpec
from webscoper.schemas.version import VersionContext


class FakeRepairLLMClient(BaseLLMClient):
    def __init__(self, target_url: str) -> None:
        self.target_url = target_url
        self.calls = 0

    async def generate(self, request: LLMRequest) -> LLMResponse:
        self.calls += 1
        if self.calls == 1:
            return LLMResponse(content="I will click the button.")
        return LLMResponse(
            content=json.dumps(
                {
                    "tool_calls": [
                        {
                            "call_id": "call_001",
                            "tool_id": "browser_open_observe",
                            "arguments": {"url": self.target_url},
                        },
                        {
                            "call_id": "call_002",
                            "tool_id": "finish_task",
                            "arguments": {"summary": "done"},
                        },
                    ]
                }
            )
        )


@pytest.mark.asyncio
async def test_llm_task_planner_repairs_invalid_tool_calls(
    tmp_path: Path,
) -> None:
    context = _context(tmp_path)
    planner = LLMTaskPlanner(
        FakeRepairLLMClient(context.task.target_url),
        repair_attempts=1,
    )

    plan = await planner.build_plan(
        context.snapshot(),
        PromptBuildResult(prompt_text="You are a browser agent."),
    )

    assert len(plan.steps) == 2
    assert len(planner.repair_requests) == 1
    assert planner.last_parse_result is not None
    assert planner.last_parse_result.status == "failed"
    assert planner.repair_parse_results[-1].status == "success"


@pytest.mark.asyncio
async def test_llm_task_planner_without_repair_raises(tmp_path: Path) -> None:
    context = _context(tmp_path)
    planner = LLMTaskPlanner(
        FakeRepairLLMClient(context.task.target_url),
        repair_attempts=0,
    )

    with pytest.raises(RuntimeError, match="TOOL_CALL_PARSE_ERROR"):
        await planner.build_plan(
            context.snapshot(),
            PromptBuildResult(prompt_text="You are a browser agent."),
        )


def _context(tmp_path: Path) -> WebAgentContext:
    task = TaskSpec(
        task_id="repair_task",
        raw_input="Open the page.",
        target_url=Path("tests/fixtures/mock_site/basic.html").resolve().as_uri(),
    )
    return WebAgentContext(
        task=task,
        run_id="repair_task",
        run_dir=tmp_path,
        trace_recorder=TraceRecorder(run_dir=tmp_path, run_id="repair_task"),
        transcript_store=TranscriptStore(run_dir=tmp_path, run_id="repair_task"),
        version=VersionContext(),
        state=RuntimeState(status="running"),
    )
