from __future__ import annotations

import importlib.util
import os
from pathlib import Path
from typing import Any

from webscoper.api.schemas import DiagnosticsResponse
from webscoper.runtime.llm.config import default_fake_router_config
from webscoper.skills.registry import create_default_skill_registry


def build_diagnostics(runs_dir: Path = Path("runs")) -> DiagnosticsResponse:
    runs_path = runs_dir.resolve()
    return DiagnosticsResponse(
        status="ok",
        runtime_backend="langgraph",
        artifact_directory=_artifact_directory_status(runs_path),
        llm=_llm_status(),
        registered_skills=_registered_skills(),
        browser=_browser_status(),
        config=_config_status(),
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
    router = default_fake_router_config()
    local_config = Path("configs/llm.local.toml")
    committed_example = Path("configs/llm.example.toml")
    return {
        "mode": "fake",
        "default_provider": router.default_provider,
        "default_model": router.default_model,
        "real_llm_enabled_by_default": False,
        "local_config_present": local_config.exists(),
        "example_config_present": committed_example.exists(),
        "api_key_required_for_default": False,
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


def _browser_status() -> dict[str, object]:
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
    }


def _config_status() -> dict[str, object]:
    return {
        "cors_origins": [
            origin.strip()
            for origin in os.getenv("VANISCOPE_CORS_ORIGINS", "http://localhost:3000").split(",")
            if origin.strip()
        ],
        "llm_env_base_url_set": bool(os.getenv("VANISCOPE_LLM_BASE_URL")),
        "llm_env_model_set": bool(os.getenv("VANISCOPE_LLM_MODEL")),
        "llm_env_api_key_set": bool(os.getenv("VANISCOPE_LLM_API_KEY")),
        "sensitive_values_redacted": True,
    }
