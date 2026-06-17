from __future__ import annotations

import json
from abc import ABC, abstractmethod
from typing import Any

from webscoper.schemas.llm import LLMRequest, LLMResponse


class BaseLLMClient(ABC):
    @abstractmethod
    async def generate(self, request: LLMRequest) -> LLMResponse:
        ...


class FakeLLMClient(BaseLLMClient):
    async def generate(self, request: LLMRequest) -> LLMResponse:
        task_id = str(request.metadata.get("task_id") or "task")
        target_url = str(request.metadata.get("target_url") or "")
        action = request.metadata.get("action")

        tool_calls: list[dict[str, Any]] = [
            {
                "call_id": "call_001",
                "tool_id": "browser_open_observe",
                "arguments": {"url": target_url},
                "reason": "Open the target page and collect the initial observation.",
            }
        ]

        if action:
            tool_calls.extend(
                [
                    {
                        "call_id": "call_002",
                        "tool_id": "browser_click_intent",
                        "arguments": {"action": action},
                        "reason": "Click the requested target and verify the expected effect.",
                    },
                    {
                        "call_id": "call_003",
                        "tool_id": "browser_extract",
                        "arguments": {},
                        "reason": "Extract visible page information after clicking.",
                    },
                    {
                        "call_id": "call_004",
                        "tool_id": "finish_task",
                        "arguments": {
                            "summary": "Click-intent browser task completed.",
                        },
                        "reason": "Finish the click-intent browser task.",
                    },
                ]
            )
        else:
            tool_calls.extend(
                [
                    {
                        "call_id": "call_002",
                        "tool_id": "browser_extract",
                        "arguments": {},
                        "reason": "Extract visible page information after opening.",
                    },
                    {
                        "call_id": "call_003",
                        "tool_id": "finish_task",
                        "arguments": {
                            "summary": "Open-only browser task completed.",
                        },
                        "reason": "Finish the open-only browser task.",
                    },
                ]
            )

        content = json.dumps(
            {
                "task_id": task_id,
                "tool_calls": tool_calls,
            },
            indent=2,
            ensure_ascii=False,
        )
        return LLMResponse(
            content=f"```json\n{content}\n```",
            model="fake-llm",
            usage={
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
            },
            raw={"client": "FakeLLMClient"},
        )
