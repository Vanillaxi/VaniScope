from __future__ import annotations

import json
from pathlib import Path

import pytest

from webscoper.runtime.execution import WebAgentExecutionHandler
from webscoper.runtime.llm_client import BaseLLMClient
from webscoper.schemas.llm import LLMRequest, LLMResponse
from webscoper.schemas.task import TaskSpec


class LazyToolLLMClient(BaseLLMClient):
    async def generate(self, request: LLMRequest) -> LLMResponse:
        return LLMResponse(
            content=json.dumps(
                {
                    "tool_calls": [
                        {
                            "call_id": "call_001",
                            "tool_id": "web_search",
                            "arguments": {"query": "playwright"},
                        }
                    ]
                }
            ),
            model="mock-real-llm",
        )


@pytest.mark.asyncio
async def test_execution_handler_blocks_invalid_plan_before_loop(
    tmp_path: Path,
) -> None:
    task = TaskSpec(
        task_id="handler_invalid_plan",
        raw_input="Search the web.",
        target_url=Path("tests/fixtures/mock_site/basic.html").resolve().as_uri(),
    )
    handler = WebAgentExecutionHandler(
        output_root=tmp_path,
        planner_mode="real_llm",
        llm_client=LazyToolLLMClient(),
    )

    with pytest.raises(RuntimeError, match="LAZY_TOOL_NOT_EXECUTABLE"):
        await handler.run(task)

    context = handler.last_context
    assert context is not None
    event_types = _jsonl_values(context.transcript_store.transcript_path, "event_type")
    assert "llm_response" in event_types
    assert "plan_built" in event_types
    assert "plan_validation_completed" in event_types
    assert "plan_validation_failed" in event_types
    assert "execution_failed" in event_types
    assert "tool_call_completed" not in event_types


def _jsonl_values(path: Path, key: str) -> list[str]:
    return [
        json.loads(line)[key]
        for line in path.read_text(encoding="utf-8").splitlines()
    ]
