from __future__ import annotations

from pathlib import Path

import pytest

from webscoper.runtime.llm.config import (
    load_llm_router_config_from_file,
    provider_config_to_client_config,
    resolve_llm_provider_config,
)


def test_load_and_resolve_llm_router_config(tmp_path: Path) -> None:
    path = _write_config(tmp_path)

    router_config = load_llm_router_config_from_file(path)
    provider = resolve_llm_provider_config(router_config)
    overridden = resolve_llm_provider_config(
        router_config,
        model_override="override-model",
    )
    client_config = provider_config_to_client_config(provider)

    assert router_config.default_provider == "deepseek"
    assert provider.provider_id == "deepseek"
    assert provider.api_key == "test-key"
    assert provider.model == "test-model"
    assert overridden.model == "override-model"
    assert client_config.base_url == "https://example.test/v1"
    assert client_config.api_key == "test-key"


def test_resolve_disabled_provider_raises(tmp_path: Path) -> None:
    path = _write_config(tmp_path, enabled=False)
    router_config = load_llm_router_config_from_file(path)

    with pytest.raises(ValueError, match="disabled"):
        resolve_llm_provider_config(router_config)


def test_resolve_unknown_provider_raises(tmp_path: Path) -> None:
    path = _write_config(tmp_path)
    router_config = load_llm_router_config_from_file(path)

    with pytest.raises(ValueError, match="Unknown LLM provider"):
        resolve_llm_provider_config(router_config, provider_id="missing")


def test_resolve_missing_api_key_raises(tmp_path: Path) -> None:
    path = _write_config(tmp_path, api_key=None)
    router_config = load_llm_router_config_from_file(path)

    with pytest.raises(ValueError, match="Missing API key"):
        resolve_llm_provider_config(router_config)


def test_resolve_api_key_env(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = _write_config(tmp_path, api_key=None, api_key_env="TEST_LLM_KEY")
    router_config = load_llm_router_config_from_file(path)
    monkeypatch.setenv("TEST_LLM_KEY", "env-key")

    provider = resolve_llm_provider_config(router_config)

    assert provider.api_key == "env-key"


def test_load_missing_file_raises(tmp_path: Path) -> None:
    path = tmp_path / "missing.toml"

    with pytest.raises(ValueError, match=str(path)):
        load_llm_router_config_from_file(path)


def _write_config(
    tmp_path: Path,
    enabled: bool = True,
    api_key: str | None = "test-key",
    api_key_env: str | None = None,
) -> Path:
    path = tmp_path / "llm.local.toml"
    key_line = f'api_key = "{api_key}"' if api_key else ""
    key_env_line = f'api_key_env = "{api_key_env}"' if api_key_env else ""
    path.write_text(
        f"""
default_provider = "deepseek"

[providers.deepseek]
enabled = {str(enabled).lower()}
provider_type = "openai_compatible"
base_url = "https://example.test/v1"
{key_line}
{key_env_line}
model = "test-model"
timeout_ms = 30000
temperature = 0.0
max_tokens = 2048
""",
        encoding="utf-8",
    )
    return path
