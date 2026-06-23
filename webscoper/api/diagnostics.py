from __future__ import annotations

import importlib.util
import os
from pathlib import Path
from typing import Any

from webscoper.api.schemas import DiagnosticsResponse
from webscoper.browser.public_web import PublicWebRuntimeConfig, load_runtime_config
from webscoper.runtime.llm.config import (
    default_llm_config_path,
    default_fake_router_config,
    load_llm_router_config_from_file,
)
from webscoper.schemas.runtime import BudgetContext
from webscoper.skills.registry import create_default_skill_registry


def build_diagnostics(
    runs_dir: Path = Path("runs"),
    web_config: PublicWebRuntimeConfig | None = None,
) -> DiagnosticsResponse:
    runs_path = runs_dir.resolve()
    web_config = web_config or load_runtime_config()
    return DiagnosticsResponse(
        status="ok",
        runtime_backend="langgraph",
        artifact_directory=_artifact_directory_status(runs_path),
        llm=_llm_status(),
        web=web_config.diagnostics_payload(),
        registered_skills=_registered_skills(),
        browser=_browser_status(web_config),
        config=_config_status(web_config),
    )


def _artifact_directory_status(runs_path: Path) -> dict[str, object]:
    exists = runs_path.exists()
    is_dir = runs_path.is_dir()
    writable = False
    if exists and is_dir:
        writable = os.access(runs_path, os.W_OK)
    elif not exists:
        parent = runs_path.parent
        writable = parent.exists() and os.access(parent, os.W_OK)
    return {
        "path": str(runs_path),
        "exists": exists,
        "is_dir": is_dir,
        "writable": writable,
    }


def _llm_status() -> dict[str, object]:
    configured_path = os.getenv("VANISCOPE_LLM_CONFIG")
    local_config = default_llm_config_path()
    expected_config = Path(configured_path or "configs/llm.local.toml")
    committed_example = Path("configs/llm.example.toml")
    warnings: list[str] = []
    config_source = None
    router = default_fake_router_config()
    real_enabled = False
    selected_provider = router.providers.get(router.default_provider)
    if local_config is not None:
        config_source = str(local_config)
        try:
            router = load_llm_router_config_from_file(local_config)
            selected_provider = router.providers.get(router.default_provider)
            real_enabled = (
                router.mode in {"real", "openai_compatible"}
                and selected_provider is not None
                and selected_provider.provider_type == "openai_compatible"
            )
            if not real_enabled:
                warnings.append(
                    "Real LLM is disabled because configs/llm.local.toml router.mode is not real."
                )
        except Exception as exc:
            router = default_fake_router_config()
            selected_provider = router.providers.get(router.default_provider)
            warnings.append(f"Failed to load local LLM config: {type(exc).__name__}")
    else:
        warnings.append(f"No {expected_config} found; fake LLM provider is active.")

    return {
        "mode": router.mode,
        "default_provider": router.default_provider,
        "default_model": router.default_model,
        "model": selected_provider.model if selected_provider is not None else router.default_model,
        "provider_type": selected_provider.provider_type if selected_provider is not None else None,
        "real_enabled": real_enabled,
        "real_llm_enabled_by_default": False,
        "local_config_present": local_config is not None,
        "example_config_present": committed_example.exists(),
        "config_source": config_source,
        "budget": _redacted_budget(
            BudgetContext().model_copy(update=router.budget).model_dump(mode="json")
        ),
        "warnings": warnings,
        "api_key_required_for_default": real_enabled,
        "api_key_configured": _api_key_configured(selected_provider) if selected_provider else False,
        "sensitive_values_redacted": True,
    }


def _registered_skills() -> list[dict[str, object]]:
    registry = create_default_skill_registry()
    return [
        {
            "skill_id": skill.definition.skill_id,
            "name": skill.definition.name,
            "version": skill.definition.version,
            "supported_task_types": skill.definition.supported_task_types,
            "required_tools": skill.definition.required_tools,
            "risk_level": skill.definition.risk_level,
        }
        for skill in registry.list_skills()
    ]


def _browser_status(public_web) -> dict[str, object]:
    playwright_importable = importlib.util.find_spec("playwright") is not None
    chromium_ready = False
    browser_check_error: str | None = None
    if playwright_importable:
        try:
            from playwright.sync_api import sync_playwright

            with sync_playwright() as playwright:
                chromium_ready = Path(playwright.chromium.executable_path).exists()
        except Exception as exc:  # pragma: no cover - environment-dependent detail.
            browser_check_error = type(exc).__name__
    return {
        "playwright_importable": playwright_importable,
        "chromium_executable_present": chromium_ready,
        "ready": playwright_importable and chromium_ready,
        "check": "local import and browser executable probe only",
        "error": browser_check_error,
        "runtime_mode": public_web.mode,
        "public_network_enabled": public_web.public_network_enabled,
        "allowed_domains": public_web.allowed_domains,
        "browser_session": {
            "default_scope": "task",
            "persist_storage_state": False,
            "storage_state_dir": ".vaniscope/browser_state",
            "max_session_age_minutes": 60,
            "allow_public_web_session_reuse": False,
            "sensitive_values_redacted": True,
        },
        "browser_recording": {
            "video_enabled": False,
            "video_dir": "runs/videos",
        },
    }


def _config_status(public_web) -> dict[str, object]:
    return {
        "cors_origins": [
            origin.strip()
            for origin in os.getenv("VANISCOPE_CORS_ORIGINS", "http://localhost:3000").split(",")
            if origin.strip()
        ],
        "llm_env_base_url_set": bool(os.getenv("VANISCOPE_LLM_BASE_URL")),
        "llm_env_model_set": bool(os.getenv("VANISCOPE_LLM_MODEL")),
        "llm_env_api_key_set": bool(os.getenv("VANISCOPE_LLM_API_KEY")),
        "runtime_mode": public_web.mode,
        "public_network_enabled": public_web.public_network_enabled,
        "allowed_domains": public_web.allowed_domains,
        "public_web_config_path": public_web.source_path,
        "sensitive_values_redacted": True,
    }


def _redacted_budget(budget: dict[str, Any]) -> dict[str, object]:
    safe_keys = {
        "max_calls_per_task",
        "max_prompt_tokens_per_call",
        "max_prompt_tokens",
        "soft_prompt_tokens_per_task",
        "approval_prompt_tokens_per_task",
        "hard_prompt_tokens_per_task",
        "max_completion_tokens_per_call",
        "max_completion_tokens",
        "max_completion_tokens_per_task",
        "max_total_tokens_per_task",
        "max_llm_calls_per_task",
        "soft_cost_usd_per_task",
        "approval_cost_usd_per_task",
        "hard_cost_usd_per_task",
        "max_cost_usd",
        "enable_budget_approval",
        "enable_auto_compaction",
        "timeout_seconds",
    }
    return {key: value for key, value in budget.items() if key in safe_keys}


def _api_key_configured(provider) -> bool:
    if provider is None:
        return False
    if provider.api_key and provider.api_key != "YOUR_API_KEY_HERE":
        return True
    if provider.api_key_env:
        return bool(os.getenv(provider.api_key_env))
    return False
