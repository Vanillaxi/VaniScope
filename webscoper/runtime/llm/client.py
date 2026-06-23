from __future__ import annotations

import asyncio
import json
import socket
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from typing import Any

from webscoper.schemas.llm import LLMClientConfig, LLMRequest, LLMResponse


class BaseLLMClient(ABC):
    @abstractmethod
    async def generate(self, request: LLMRequest) -> LLMResponse:
        ...


class LLMProviderTimeoutError(RuntimeError):
    def __init__(self, message: str = "The read operation timed out") -> None:
        super().__init__(message)
        self.error_type = "LLM_PROVIDER_TIMEOUT"
        self.retryable = True


class FakeLLMClient(BaseLLMClient):
    async def generate(self, request: LLMRequest) -> LLMResponse:
        if request.metadata.get("response_format") == "auto_explore_action":
            return _fake_auto_explore_response(request)

        task_id = str(request.metadata.get("task_id") or "task")
        target_url = str(request.metadata.get("target_url") or "")
        action = request.metadata.get("action")

        tool_calls: list[dict[str, Any]] = [
            {
                "call_id": "call_001",
                "tool_id": "browser_open",
                "arguments": {"url": target_url},
                "reason": "Open the target page.",
            },
            {
                "call_id": "call_002",
                "tool_id": "browser_observe",
                "arguments": {"include_screenshot": True},
                "reason": "Collect the initial page observation.",
            },
        ]

        if action:
            tool_calls.extend(
                [
                    {
                        "call_id": "call_003",
                        "tool_id": "browser_click",
                        "arguments": _fake_click_arguments(action),
                        "reason": "Click the requested target and verify the expected effect.",
                    },
                    {
                        "call_id": "call_004",
                        "tool_id": "browser_extract",
                        "arguments": {},
                        "reason": "Extract visible page information after clicking.",
                    },
                    {
                        "call_id": "call_005",
                        "tool_id": "finish_task",
                        "arguments": {
                            "summary_instruction": "Browser click task completed.",
                        },
                        "reason": "Finish the browser click task.",
                    },
                ]
            )
        else:
            tool_calls.extend(
                [
                    {
                        "call_id": "call_003",
                        "tool_id": "browser_extract",
                        "arguments": {},
                        "reason": "Extract visible page information after opening.",
                    },
                    {
                        "call_id": "call_004",
                        "tool_id": "finish_task",
                        "arguments": {
                            "summary_instruction": "Open-only browser task completed.",
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


def _fake_click_arguments(action: Any) -> dict[str, Any]:
    if isinstance(action, dict):
        return {
            "target_hint": str(action.get("target_hint") or action.get("intent") or ""),
            "expected_effect": action.get("expected_effect")
            if isinstance(action.get("expected_effect"), dict)
            else {"type": "none"},
        }
    return {"target_hint": str(action), "expected_effect": {"type": "none"}}


def _fake_auto_explore_response(request: LLMRequest) -> LLMResponse:
    goal = str(request.metadata.get("goal") or "").lower()
    history = request.metadata.get("history")
    history_items = history if isinstance(history, list) else []
    action_types = [
        str(item.get("action_type") or item.get("tool_id") or "")
        for item in history_items
        if isinstance(item, dict)
    ]

    if "selector_action" in goal:
        payload = {
            "reasoning_summary": "Try to return a forbidden selector for validation tests.",
            "action": {
                "type": "click_intent",
                "target_hint": "css=#quickstart",
                "expected_effect": {"type": "content_or_url_changes", "value": "install"},
                "risk_level": "read_only",
            },
        }
    elif "invalid_action" in goal or "非法 action" in goal:
        payload: dict[str, Any] = {
            "reasoning_summary": "Return an invalid action for schema validation tests.",
            "action": {"type": "navigate", "target_hint": "invalid"},
        }
    elif "delete" in goal or "删除" in goal:
        payload = {
            "reasoning_summary": "The goal asks for a risky delete-like action.",
            "action": {
                "type": "click_intent",
                "target_hint": "Delete",
                "expected_effect": {"type": "content_or_url_changes", "value": "delete"},
                "risk_level": "high",
            },
        }
    elif (
        ("click" in goal or "repositories" in goal or "仓库" in goal)
        and "browser_click" not in action_types
    ):
        target = "Repositories" if "repositories" in goal or "仓库" in goal else "Quickstart"
        payload = {
            "reasoning_summary": "A related navigation target is available and useful.",
            "action": {
                "type": "click_intent",
                "target_hint": target,
                "expected_effect": {
                    "type": "content_or_url_changes",
                    "value": target.lower(),
                },
                "risk_level": "read_only",
            },
        }
    elif "browser_extract" not in action_types:
        payload = {
            "reasoning_summary": "The visible page contains enough information to extract.",
            "action": {"type": "extract", "risk_level": "read_only"},
        }
    else:
        payload = {
            "reasoning_summary": "Enough evidence has been collected to finish.",
            "action": {
                "type": "finish",
                "summary": "Auto exploration completed with collected evidence.",
                "risk_level": "read_only",
            },
        }

    return LLMResponse(
        content=json.dumps(payload, indent=2, ensure_ascii=False),
        model="fake-llm",
        usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        raw={"client": "FakeLLMClient", "mode": "auto_explore"},
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
        headers = {
            **_safe_extra_headers(self.config.extra_headers),
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
        }
        http_request = urllib.request.Request(
            url,
            data=body,
            headers=headers,
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
            if _is_timeout_reason(exc.reason):
                raise LLMProviderTimeoutError(_timeout_message(exc.reason)) from exc
            raise RuntimeError(f"LLM HTTP request failed: {exc.reason}") from exc
        except (TimeoutError, socket.timeout) as exc:
            raise LLMProviderTimeoutError(_timeout_message(exc)) from exc

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


def _is_timeout_reason(reason: object) -> bool:
    if isinstance(reason, (TimeoutError, socket.timeout)):
        return True
    return "timed out" in str(reason).lower()


def _timeout_message(reason: object) -> str:
    message = str(reason) or "The read operation timed out"
    return "The read operation timed out" if "timed out" in message.lower() else message


def _safe_extra_headers(headers: dict[str, str]) -> dict[str, str]:
    return {
        key: value
        for key, value in headers.items()
        if key.lower() != "authorization"
    }
