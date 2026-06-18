from __future__ import annotations

import json
from pathlib import Path

import pytest

from webscoper.runtime.execution.handler import WebAgentExecutionHandler
from webscoper.runtime.llm.client import BaseLLMClient
from webscoper.schemas.action import ActionContract, ExpectedEffect
from webscoper.schemas.llm import LLMRequest, LLMResponse
from webscoper.schemas.task import TaskSpec


class MockLLMClient(BaseLLMClient):
    async def generate(self, request: LLMRequest) -> LLMResponse:
        action = request.metadata["action"]
        target_url = request.metadata["target_url"]
        return LLMResponse(
            content=json.dumps(
                {
                    "tool_calls": [
                        {
                            "call_id": "call_001",
                            "tool_id": "browser_open_observe",
                            "arguments": {"url": target_url},
                        },
                        {
                            "call_id": "call_002",
                            "tool_id": "browser_click_intent",
                            "arguments": {"action": action},
                        },
                        {
                            "call_id": "call_003",
                            "tool_id": "browser_extract",
                            "arguments": {},
                        },
                        {
                            "call_id": "call_004",
                            "tool_id": "finish_task",
                            "arguments": {"summary": "done"},
                        },
                    ]
                }
            ),
            model="mock-real-llm",
        )


@pytest.mark.asyncio
async def test_execution_handler_real_llm_with_mock_client(tmp_path: Path) -> None:
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
        task_id="handler_real_llm_mock",
        raw_input="Open local basic mock and click Quickstart.",
        target_url=Path("tests/fixtures/mock_site/basic.html").resolve().as_uri(),
        action=action,
        expected_effect=action.expected_effect,
    )
    handler = WebAgentExecutionHandler(
        output_root=tmp_path,
        planner_mode="real_llm",
        llm_client=MockLLMClient(),
        repair_attempts=1,
    )

    observation = await handler.run(task)

    context = handler.last_context
    assert context is not None
    assert "pip install playwright" in observation.visible_text_summary

    event_types = _jsonl_values(context.transcript_store.transcript_path, "event_type")
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
