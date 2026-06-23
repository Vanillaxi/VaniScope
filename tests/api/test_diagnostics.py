from __future__ import annotations

import webscoper.api.app as api_module
from webscoper.api.diagnostics import build_diagnostics
from webscoper.api.runner_factory import build_handler
from webscoper.api.schemas import TaskCreateRequest
from webscoper.api.task_service import TaskService


def test_api_diagnostics_returns_local_runtime_status(api_client) -> None:
    response = api_client.get("/diagnostics")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["service"] == "vaniscope-api"
    assert payload["runtime_backend"] == "langgraph"
    assert payload["artifact_directory"]["writable"] is True
    assert payload["web"]["mode"] == "local"
    assert payload["web"]["public_network_enabled"] is False
    assert payload["web"]["allowed_domains"] == []
    assert payload["llm"]["mode"] == "fake"
    assert payload["llm"]["real_llm_enabled_by_default"] is False
    assert payload["llm"]["api_key_required_for_default"] is False
    assert {
        skill["skill_id"] for skill in payload["registered_skills"]
    } == {"docs_research", "github_issue_research"}
    assert "playwright_importable" in payload["browser"]
    assert payload["config"]["sensitive_values_redacted"] is True
    assert "VANISCOPE_LLM_API_KEY" not in str(payload)


def test_api_diagnostics_returns_loaded_runtime_local_config(
    api_client,
    tmp_path,
) -> None:
    runtime_local = tmp_path / "runtime.local.toml"
    runtime_local.write_text(
        "\n".join(
            [
                "[web]",
                'mode = "public_safe"',
                "public_network_enabled = true",
                'allowed_domains = ["github.com"]',
                "max_pages_per_task = 3",
                "request_delay_ms = 250",
                "navigation_timeout_ms = 12000",
            ]
        ),
        encoding="utf-8",
    )
    api_module.task_service = TaskService(
        runs_dir=tmp_path / "runs",
        runtime_config_path=runtime_local,
    )

    response = api_client.get("/diagnostics")

    assert response.status_code == 200
    web = response.json()["web"]
    assert web["mode"] == "public_safe"
    assert web["public_network_enabled"] is True
    assert web["allowed_domains"] == ["github.com"]
    assert web["navigation_timeout_ms"] == 12000
    assert web["source_path"] == str(runtime_local)


def test_diagnostics_exposes_llm_timeout_and_fallback_without_secrets(
    tmp_path,
    monkeypatch,
) -> None:
    llm_local = tmp_path / "llm.local.toml"
    llm_local.write_text(
        "\n".join(
            [
                "[router]",
                'mode = "real"',
                'default_provider = "qwen"',
                "",
                "[llm]",
                "max_retries_per_call = 1",
                "retry_on_timeout = true",
                "",
                "[providers.qwen]",
                'type = "openai_compatible"',
                'base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"',
                'api_key_env = "DASHSCOPE_API_KEY"',
                'model = "qwen-plus"',
                'fallback_model = "qwen-turbo"',
                "timeout_seconds = 90",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("VANISCOPE_LLM_CONFIG", str(llm_local))
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)

    payload = build_diagnostics(runs_dir=tmp_path / "runs").model_dump(mode="json")

    llm = payload["llm"]
    assert llm["provider"] == "qwen"
    assert llm["timeout_ms"] == 90000
    assert llm["fallback_model"] == "qwen-turbo"
    assert llm["budget"]["max_llm_retries_per_call"] == 1
    assert llm["budget"]["retry_on_llm_timeout"] is True
    assert llm["api_key_configured"] is False
    assert "DASHSCOPE_API_KEY" not in str(payload["llm"])


def test_task_service_loaded_web_config_is_passed_to_handler(tmp_path) -> None:
    runtime_local = tmp_path / "runtime.local.toml"
    runtime_local.write_text(
        "\n".join(
            [
                "[web]",
                'mode = "public_safe"',
                "public_network_enabled = true",
                'allowed_domains = ["github.com"]',
            ]
        ),
        encoding="utf-8",
    )
    service = TaskService(
        runs_dir=tmp_path / "runs",
        runtime_config_path=runtime_local,
    )

    handler = build_handler(
        service,
        "task_public_safe",
        TaskCreateRequest(url="https://github.com/Vanillaxi"),
    )

    assert handler.public_web_config.mode == "public_safe"
    assert handler.public_web_config.public_network_enabled is True
    assert handler.public_web_config.allowed_domains == ["github.com"]
