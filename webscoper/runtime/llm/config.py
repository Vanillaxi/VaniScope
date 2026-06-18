from __future__ import annotations

import os
import tomllib
from pathlib import Path

from pydantic import ValidationError

from webscoper.schemas.llm import (
    LLMClientConfig,
    LLMProviderConfig,
    LLMRouterConfig,
)


def load_llm_config_from_env(
    model_override: str | None = None,
) -> LLMClientConfig:
    base_url = os.environ.get("VANISCOPE_LLM_BASE_URL")
    api_key = os.environ.get("VANISCOPE_LLM_API_KEY")
    model = model_override or os.environ.get("VANISCOPE_LLM_MODEL")
    timeout_ms = _timeout_ms(os.environ.get("VANISCOPE_LLM_TIMEOUT_MS"))

    if not base_url:
        raise ValueError("Missing VANISCOPE_LLM_BASE_URL")
    if not api_key:
        raise ValueError("Missing VANISCOPE_LLM_API_KEY")
    if not model:
        raise ValueError("Missing VANISCOPE_LLM_MODEL")

    return LLMClientConfig(
        base_url=base_url,
        api_key=api_key,
        model=model,
        timeout_ms=timeout_ms,
    )


def load_llm_router_config_from_file(path: Path) -> LLMRouterConfig:
    if not path.exists():
        raise ValueError(f"LLM config file does not exist: {path}")

    try:
        payload = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise ValueError(f"Failed to parse LLM config file: {path}") from exc

    default_provider = payload.get("default_provider")
    if not default_provider:
        raise ValueError("LLM config must include default_provider")

    providers_payload = payload.get("providers")
    if not isinstance(providers_payload, dict) or not providers_payload:
        raise ValueError("LLM config must include at least one providers section")

    providers: dict[str, LLMProviderConfig] = {}
    for provider_id, provider_payload in providers_payload.items():
        if not isinstance(provider_payload, dict):
            raise ValueError(f"Provider config must be a table: {provider_id}")
        try:
            providers[provider_id] = LLMProviderConfig.model_validate(
                {
                    **provider_payload,
                    "provider_id": provider_id,
                }
            )
        except ValidationError as exc:
            raise ValueError(f"Invalid provider config: {provider_id}") from exc

    return LLMRouterConfig(
        default_provider=str(default_provider),
        providers=providers,
    )


def resolve_llm_provider_config(
    router_config: LLMRouterConfig,
    provider_id: str | None = None,
    model_override: str | None = None,
) -> LLMProviderConfig:
    selected_provider_id = provider_id or router_config.default_provider
    provider = router_config.providers.get(selected_provider_id)
    if provider is None:
        raise ValueError(f"Unknown LLM provider: {selected_provider_id}")
    if not provider.enabled:
        raise ValueError(f"LLM provider is disabled: {selected_provider_id}")

    api_key = provider.api_key
    if not api_key and provider.api_key_env:
        api_key = os.environ.get(provider.api_key_env)
    if not api_key:
        raise ValueError(f"Missing API key for LLM provider: {selected_provider_id}")

    return provider.model_copy(
        update={
            "api_key": api_key,
            "model": model_override or provider.model,
        }
    )


def provider_config_to_client_config(provider: LLMProviderConfig) -> LLMClientConfig:
    if not provider.api_key:
        raise ValueError(f"Missing API key for LLM provider: {provider.provider_id}")
    return LLMClientConfig(
        provider=provider.provider_type,
        base_url=provider.base_url,
        api_key=provider.api_key,
        model=provider.model,
        timeout_ms=provider.timeout_ms,
        temperature=provider.temperature,
        max_tokens=provider.max_tokens,
        extra_headers=provider.extra_headers,
    )


def _timeout_ms(value: str | None) -> int:
    if not value:
        return 30000
    try:
        timeout_ms = int(value)
    except ValueError as exc:
        raise ValueError("VANISCOPE_LLM_TIMEOUT_MS must be an integer") from exc
    if timeout_ms <= 0:
        raise ValueError("VANISCOPE_LLM_TIMEOUT_MS must be positive")
    return timeout_ms
