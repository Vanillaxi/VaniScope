from __future__ import annotations

from pathlib import Path

import pytest

from webscoper.runtime.llm_client import OpenAICompatibleLLMClient
from webscoper.runtime.llm_router import LLMProviderRouter


def test_llm_provider_router_creates_openai_compatible_client(tmp_path: Path) -> None:
    path = _write_config(tmp_path)

    client = LLMProviderRouter(path).create_client(provider_id="deepseek")

    assert isinstance(client, OpenAICompatibleLLMClient)
    assert client.config.base_url == "https://example.test/v1"
    assert client.config.model == "test-model"


def test_llm_provider_router_unsupported_provider_type_raises(tmp_path: Path) -> None:
    path = _write_config(tmp_path, provider_type="native_only")

    with pytest.raises(ValueError, match="Unsupported LLM provider_type") as exc_info:
        LLMProviderRouter(path).create_client(provider_id="deepseek")

    assert "test-key" not in str(exc_info.value)


def test_llm_provider_router_disabled_provider_raises(tmp_path: Path) -> None:
    path = _write_config(tmp_path, enabled=False)

    with pytest.raises(ValueError, match="disabled") as exc_info:
        LLMProviderRouter(path).create_client(provider_id="deepseek")

    assert "test-key" not in str(exc_info.value)


def _write_config(
    tmp_path: Path,
    enabled: bool = True,
    provider_type: str = "openai_compatible",
) -> Path:
    path = tmp_path / "llm.local.toml"
    path.write_text(
        f"""
default_provider = "deepseek"

[providers.deepseek]
enabled = {str(enabled).lower()}
provider_type = "{provider_type}"
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
