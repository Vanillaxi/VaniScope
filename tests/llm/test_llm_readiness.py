from __future__ import annotations

import json
from pathlib import Path

import pytest

from webscoper.runtime.execution.handler import WebAgentExecutionHandler
from webscoper.api.runner_factory import build_handler, resolve_request_planner_mode
from webscoper.api.schemas import TaskCreateRequest
from webscoper.api.task_service import TaskService
from webscoper.api.diagnostics import build_diagnostics
from webscoper.runtime.llm.client import BaseLLMClient, FakeLLMClient
from webscoper.runtime.llm.auto_explore import AutoExploreActionPlanner
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
    assert config.providers["openai_compatible"].api_key == "YOUR_API_KEY_HERE"
    assert config.providers["openai_compatible"].timeout_ms == 30000
    assert config.budget["max_llm_calls_per_task"] == 8


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


def test_diagnostics_reports_real_llm_without_leaking_key(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = tmp_path / "llm.local.toml"
    config_path.write_text(
        """
[router]
default_provider = "openai_compatible"
mode = "real"

[providers.openai_compatible]
type = "openai_compatible"
base_url = "https://example.test/v1"
api_key = "super-secret-test-key"
model = "test-model"
timeout_seconds = 10
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("VANISCOPE_LLM_CONFIG", str(config_path))

    payload = build_diagnostics(runs_dir=tmp_path / "runs").model_dump(mode="json")

    assert payload["llm"]["mode"] == "real"
    assert payload["llm"]["real_enabled"] is True
    assert payload["llm"]["default_provider"] == "openai_compatible"
    assert payload["llm"]["model"] == "test-model"
    assert "super-secret-test-key" not in json.dumps(payload)


def test_default_auto_explore_planner_stays_deterministic_without_real_config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("VANISCOPE_LLM_CONFIG", str(tmp_path / "missing.toml"))

    request = TaskCreateRequest(
        url="tests/fixtures/mock_site/basic.html",
        mode="auto_explore",
        task_type="browser_task",
    )

    assert resolve_request_planner_mode(request) == "deterministic"


def test_request_planner_mode_real_llm_selects_real_planner(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = _write_real_llm_config(tmp_path)
    monkeypatch.setenv("VANISCOPE_LLM_CONFIG", str(config_path))
    service = TaskService(runs_dir=tmp_path / "runs")

    handler = build_handler(
        service,
        "task_real_explicit",
        TaskCreateRequest(
            url="tests/fixtures/mock_site/basic.html",
            mode="auto_explore",
            task_type="browser_task",
            planner_mode="real_llm",
        ),
    )

    assert handler.planner_mode == "real_llm"
    assert handler.llm_config_path == config_path


def test_auto_explore_uses_real_llm_when_diagnostics_configured(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_path = _write_real_llm_config(tmp_path)
    monkeypatch.setenv("VANISCOPE_LLM_CONFIG", str(config_path))
    request = TaskCreateRequest(
        url="tests/fixtures/mock_site/basic.html",
        mode="auto_explore",
        task_type="browser_task",
    )

    diagnostics = build_diagnostics(runs_dir=tmp_path / "runs").model_dump(mode="json")

    assert diagnostics["llm"]["mode"] == "real"
    assert diagnostics["llm"]["api_key_configured"] is True
    assert resolve_request_planner_mode(request) == "real_llm"


@pytest.mark.asyncio
async def test_planner_started_event_includes_real_provider_model_without_key(
    tmp_path: Path,
) -> None:
    config_path = _write_real_llm_config(tmp_path)
    events: list[dict] = []
    task = TaskSpec(
        task_id="real_event_task",
        raw_input="Summarize the page.",
        target_url=Path("tests/fixtures/mock_site/basic.html").resolve().as_uri(),
        mode="auto_explore",
        goal="Summarize the page.",
    )
    handler = WebAgentExecutionHandler(
        output_root=tmp_path,
        planner_mode="real_llm",
        llm_config_path=config_path,
        event_sink=lambda kind, message, payload: events.append(
            {"kind": kind, "message": message, "payload": payload}
        ),
    )
    context = handler.build_context(task)
    prompt_result = handler.build_prompt(context)

    await handler.plan_task(context, prompt_result)

    planner_started = [event for event in events if event["kind"] == "planner_started"][0]
    assert planner_started["payload"]["planner_mode"] == "real_llm"
    assert planner_started["payload"]["provider"] == "qwen"
    assert planner_started["payload"]["model"] == "qwen3.6-plus"
    assert "super-secret-test-key" not in json.dumps(events)


def test_real_llm_request_without_config_returns_clear_error(
    api_client,
) -> None:
    response = api_client.post(
        "/tasks/async",
        json={
            "url": "tests/fixtures/mock_site/basic.html",
            "mode": "auto_explore",
            "task_type": "browser_task",
            "planner_mode": "real_llm",
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == (
        "Real LLM requested but default provider is not configured."
    )


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
async def test_auto_explore_invalid_json_repairs_once(tmp_path: Path) -> None:
    class RepairingClient(BaseLLMClient):
        def __init__(self) -> None:
            self.calls = 0

        async def generate(self, request: LLMRequest) -> LLMResponse:
            self.calls += 1
            if self.calls == 1:
                return LLMResponse(content="not-json", model="test")
            return LLMResponse(
                content=json.dumps(
                    {
                        "reasoning_summary": "Extract enough visible information.",
                        "action": {"type": "extract", "risk_level": "read_only"},
                    }
                ),
                model="test",
            )

    task = TaskSpec(
        task_id="repair_task",
        raw_input="Open local mock page.",
        target_url=Path("tests/fixtures/mock_site/basic.html").resolve().as_uri(),
        mode="auto_explore",
        goal="Summarize the page.",
    )
    context = WebAgentExecutionHandler(output_root=tmp_path).build_context(task)
    client = RepairingClient()
    planner = AutoExploreActionPlanner(client, repair_attempts=1)

    decision = await planner.decide(
        context=context.snapshot(),
        observation=None,
        history=[],
        step_index=1,
    )

    assert decision.action.type == "extract"
    assert client.calls == 2
    assert planner.validation_errors[0]["phase"] == "initial"


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


def _write_real_llm_config(tmp_path: Path) -> Path:
    config_path = tmp_path / "llm.local.toml"
    config_path.write_text(
        """
[router]
default_provider = "qwen"
mode = "real"

[providers.qwen]
type = "openai_compatible"
base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"
api_key = "super-secret-test-key"
model = "qwen3.6-plus"
timeout_seconds = 10
""",
        encoding="utf-8",
    )
    return config_path
