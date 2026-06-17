from __future__ import annotations

import pytest

from webscoper.runtime.llm_client import FakeLLMClient
from webscoper.schemas.llm import LLMRequest


@pytest.mark.asyncio
async def test_fake_llm_client_returns_open_only_tool_calls() -> None:
    response = await FakeLLMClient().generate(
        LLMRequest(
            metadata={
                "task_id": "fake_open",
                "target_url": "file:///tmp/basic.html",
                "action": None,
            }
        )
    )

    assert "browser_open_observe" in response.content
    assert "browser_extract" in response.content
    assert "finish_task" in response.content
    assert "browser_click_intent" not in response.content


@pytest.mark.asyncio
async def test_fake_llm_client_returns_click_tool_calls() -> None:
    response = await FakeLLMClient().generate(
        LLMRequest(
            metadata={
                "task_id": "fake_click",
                "target_url": "file:///tmp/basic.html",
                "action": {
                    "action_type": "click",
                    "intent": "Click Quickstart",
                    "target_hint": "Quickstart",
                    "risk_level": "read_only",
                },
            }
        )
    )

    assert "browser_open_observe" in response.content
    assert "browser_click_intent" in response.content
    assert "browser_extract" in response.content
    assert "finish_task" in response.content
