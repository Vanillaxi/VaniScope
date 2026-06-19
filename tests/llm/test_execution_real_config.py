from __future__ import annotations

import json
from pathlib import Path

import pytest

from webscoper.runtime.execution.handler import WebAgentExecutionHandler
from webscoper.runtime.llm.client import BaseLLMClient
from webscoper.runtime.llm.router import LLMProviderRouter
from webscoper.schemas.browser import ActionContract, ExpectedEffect
from webscoper.schemas.llm import LLMRequest, LLMResponse
from webscoper.schemas.task import TaskSpec


class ConfigMockLLMClient(BaseLLMClient):
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
            model="config-mock-llm",
        )


@pytest.mark.asyncio
async def test_execution_handler_real_llm_uses_config_router(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = _write_config(tmp_path)
    captured: dict[str, object] = {}

    def fake_create_client(
        self: LLMProviderRouter,
        provider_id: str | None = None,
        model_override: str | None = None,
    ) -> BaseLLMClient:
        captured["provider_id"] = provider_id
        captured["model_override"] = model_override
        return ConfigMockLLMClient()

    monkeypatch.setattr(LLMProviderRouter, "create_client", fake_create_client)
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
        task_id="handler_real_llm_config",
        raw_input="Open local basic mock and click Quickstart.",
        target_url=Path("tests/fixtures/mock_site/basic.html").resolve().as_uri(),
        action=action,
        expected_effect=action.expected_effect,
    )
    handler = WebAgentExecutionHandler(
        output_root=tmp_path / "runs",
        planner_mode="real_llm",
        llm_config_path=config_path,
        llm_provider="deepseek",
    )

    observation = await handler.run(task)

    context = handler.last_context
    assert context is not None
    assert "pip install playwright" in observation.visible_text_summary
    assert captured["provider_id"] == "deepseek"

    transcript_text = context.transcript_store.transcript_path.read_text(
        encoding="utf-8",
    )
    event_types = [
        json.loads(line)["event_type"]
        for line in transcript_text.splitlines()
    ]
    assert "llm_request" in event_types
    assert "llm_response" in event_types
    assert "plan_built" in event_types
    assert "plan_validation_completed" in event_types
    assert "tool_call_completed" in event_types
    assert "execution_completed" in event_types
    assert "test-key" not in transcript_text


def _write_config(tmp_path: Path) -> Path:
    path = tmp_path / "llm.local.toml"
    path.write_text(
        """
default_provider = "deepseek"

[providers.deepseek]
enabled = true
provider_type = "openai_compatible"
base_url = "https://example.test/v1"
api_key = "test-key"
model = "test-model"
timeout_ms = 30000
temperature = 0.0
max_tokens = 2048
""",
        encoding="utf-8",
    )
    return path
