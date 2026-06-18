from __future__ import annotations

import pytest

from webscoper.runtime.llm.config import load_llm_config_from_env


def test_load_llm_config_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VANISCOPE_LLM_BASE_URL", "https://example.com/v1")
    monkeypatch.setenv("VANISCOPE_LLM_API_KEY", "secret")
    monkeypatch.setenv("VANISCOPE_LLM_MODEL", "example-model")
    monkeypatch.setenv("VANISCOPE_LLM_TIMEOUT_MS", "12000")

    config = load_llm_config_from_env()

    assert config.base_url == "https://example.com/v1"
    assert config.api_key == "secret"
    assert config.model == "example-model"
    assert config.timeout_ms == 12000


def test_load_llm_config_model_override_wins(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("VANISCOPE_LLM_BASE_URL", "https://example.com/v1")
    monkeypatch.setenv("VANISCOPE_LLM_API_KEY", "secret")
    monkeypatch.setenv("VANISCOPE_LLM_MODEL", "env-model")

    config = load_llm_config_from_env(model_override="override-model")

    assert config.model == "override-model"


def test_load_llm_config_missing_base_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("VANISCOPE_LLM_BASE_URL", raising=False)
    monkeypatch.setenv("VANISCOPE_LLM_API_KEY", "secret")
    monkeypatch.setenv("VANISCOPE_LLM_MODEL", "example-model")

    with pytest.raises(ValueError, match="Missing VANISCOPE_LLM_BASE_URL"):
        load_llm_config_from_env()


def test_load_llm_config_missing_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VANISCOPE_LLM_BASE_URL", "https://example.com/v1")
    monkeypatch.delenv("VANISCOPE_LLM_API_KEY", raising=False)
    monkeypatch.setenv("VANISCOPE_LLM_MODEL", "example-model")

    with pytest.raises(ValueError, match="Missing VANISCOPE_LLM_API_KEY"):
        load_llm_config_from_env()


def test_load_llm_config_missing_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VANISCOPE_LLM_BASE_URL", "https://example.com/v1")
    monkeypatch.setenv("VANISCOPE_LLM_API_KEY", "secret")
    monkeypatch.delenv("VANISCOPE_LLM_MODEL", raising=False)

    with pytest.raises(ValueError, match="Missing VANISCOPE_LLM_MODEL"):
        load_llm_config_from_env()
