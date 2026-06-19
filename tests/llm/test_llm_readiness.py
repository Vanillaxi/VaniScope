from __future__ import annotations

import json
from pathlib import Path

import pytest

from webscoper.runtime.execution.handler import WebAgentExecutionHandler
from webscoper.runtime.llm.client import BaseLLMClient, FakeLLMClient
from webscoper.runtime.llm.config import load_llm_router_config_from_file
from webscoper.runtime.llm.router import AuditedBudgetedLLMClient, LLMProviderRouter
from webscoper.schemas.llm import LLMMessage, LLMRequest, LLMResponse
from webscoper.schemas.runtime import BudgetContext
from webscoper.schemas.task import TaskSpec


def test_router_without_local_config_falls_back_to_fake_provider() -> None:
    client = LLMProviderRouter().create_client()

    assert isinstance(client, AuditedBudgetedLLMClient)
    assert isinstance(client.client, FakeLLMClient)
    assert client.provider == "fake"
    assert client.mode == "fake"


def test_example_llm_config_parses() -> None:
    config = load_llm_router_config_from_file(Path("configs/llm.example.toml"))

    assert config.default_provider == "fake"
    assert config.mode == "fake"
    assert config.providers["fake"].provider_type == "fake"
    assert config.providers["openai"].api_key == "replace-me"


def test_real_provider_requires_real_router_mode(tmp_path: Path) -> None:
    config_path = tmp_path / "llm.local.toml"
    config_path.write_text(
        """
[router]
default_provider = "openai"
mode = "fake"

[providers.openai]
type = "openai_compatible"
base_url = "https://example.test/v1"
api_key = "test-key"
model = "test-model"
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match='router.mode = "real"'):
        LLMProviderRouter(config_path).create_client()


@pytest.mark.asyncio
async def test_llm_call_audit_jsonl_written(tmp_path: Path) -> None:
    client = LLMProviderRouter().create_client(
        run_dir=tmp_path,
        task_id="audit_task",
        purpose="planner",
    )

    await client.generate(
        LLMRequest(
            messages=[LLMMessage(role="user", content="Open a local page.")],
            metadata={"task_id": "audit_task", "target_url": "file:///tmp/a.html"},
        )
    )

    records = [
        json.loads(line)
        for line in (tmp_path / "llm_calls.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert records[0]["task_id"] == "audit_task"
    assert records[0]["provider"] == "fake"
    assert records[0]["purpose"] == "planner"
    assert records[0]["status"] == "success"
    assert "api_key" not in records[0]


@pytest.mark.asyncio
async def test_budget_blocks_llm_call_and_audits_skip(tmp_path: Path) -> None:
    class ExplodingClient(BaseLLMClient):
        async def generate(self, request: LLMRequest) -> LLMResponse:
            raise AssertionError("budget should stop before the client is called")

    client = AuditedBudgetedLLMClient(
        ExplodingClient(),
        provider="mock",
        model="mock",
        mode="fake",
        audit_path=tmp_path / "llm_calls.jsonl",
        task_id="budget_task",
        purpose="planner",
        budget=BudgetContext(max_prompt_tokens=1),
    )

    with pytest.raises(RuntimeError, match="LLM budget exceeded"):
        await client.generate(
            LLMRequest(messages=[LLMMessage(role="user", content="too many tokens")])
        )

    record = json.loads((tmp_path / "llm_calls.jsonl").read_text(encoding="utf-8"))
    assert record["status"] == "skipped"
    assert record["error_type"] == "LLM_BUDGET_EXCEEDED"
    assert record["budget_decision"] == "max_prompt_tokens_exceeded"


@pytest.mark.asyncio
async def test_dry_run_writes_prompt_preview_and_skips_llm(tmp_path: Path) -> None:
    task = TaskSpec(
        task_id="dry_run_task",
        raw_input="Open local mock page.",
        target_url=Path("tests/fixtures/mock_site/basic.html").resolve().as_uri(),
    )
    handler = WebAgentExecutionHandler(
        output_root=tmp_path,
        planner_mode="fake_llm",
        dry_run=True,
    )

    observation = await handler.run(task)

    context = handler.last_context
    assert context is not None
    assert observation.title == "Dry run"
    assert (context.run_dir / "prompt_preview.md").exists()
    assert (context.run_dir / "prompt_context.json").exists()
    assert (context.run_dir / "dry_run_result.json").exists()
    assert not (context.run_dir / "llm_calls.jsonl").exists()
