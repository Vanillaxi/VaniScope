from __future__ import annotations

import json
import urllib.error
import urllib.request
import asyncio
from abc import ABC, abstractmethod
from typing import Any

from webscoper.schemas.llm import LLMClientConfig, LLMRequest, LLMResponse


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


class OpenAICompatibleLLMClient(BaseLLMClient):
    def __init__(self, config: LLMClientConfig) -> None:
        self.config = config

    async def generate(self, request: LLMRequest) -> LLMResponse:
        return await asyncio.to_thread(self._generate_sync, request)

    def _generate_sync(self, request: LLMRequest) -> LLMResponse:
        url = f"{self.config.base_url.rstrip('/')}/chat/completions"
        model = _request_model(request.model, self.config.model)
        payload = {
            "model": model,
            "messages": [
                message.model_dump(mode="json")
                for message in request.messages
            ],
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
        }
        body = json.dumps(payload).encode("utf-8")
        http_request = urllib.request.Request(
            url,
            data=body,
            headers={
                "Authorization": f"Bearer {self.config.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(
                http_request,
                timeout=self.config.timeout_ms / 1000,
            ) as response:
                response_body = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            raise RuntimeError(
                f"LLM HTTP request failed with status {exc.code}."
            ) from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"LLM HTTP request failed: {exc.reason}") from exc

        try:
            data = json.loads(response_body)
        except json.JSONDecodeError as exc:
            raise RuntimeError("LLM response was not valid JSON.") from exc

        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError("LLM response did not include choices[0].message.content.") from exc

        if not isinstance(content, str):
            raise RuntimeError("LLM response content must be a string.")

        usage = data.get("usage") if isinstance(data, dict) else None
        return LLMResponse(
            content=content,
            model=str(data.get("model") or payload["model"]),
            usage=usage if isinstance(usage, dict) else {},
            raw={
                "provider": self.config.provider,
                "base_url": self.config.base_url,
                "choices_count": len(data.get("choices", []))
                if isinstance(data.get("choices"), list)
                else 0,
            },
        )


def _request_model(request_model: str | None, config_model: str) -> str:
    if request_model and request_model not in {"none", "fake-llm"}:
        return request_model
    return config_model
