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

    router_payload = payload.get("router") if isinstance(payload.get("router"), dict) else {}
    default_provider = router_payload.get("default_provider") or payload.get("default_provider")
    if not default_provider:
        raise ValueError("LLM config must include default_provider")
    default_model = router_payload.get("default_model") or payload.get("default_model")
    mode = router_payload.get("mode") or payload.get("mode") or "real"

    providers_payload = payload.get("providers")
    if not isinstance(providers_payload, dict) or not providers_payload:
        raise ValueError("LLM config must include at least one providers section")

    providers: dict[str, LLMProviderConfig] = {}
    for provider_id, provider_payload in providers_payload.items():
        if not isinstance(provider_payload, dict):
            raise ValueError(f"Provider config must be a table: {provider_id}")
        normalized_provider = _normalize_provider_payload(provider_payload)
        provider_type = normalized_provider.get("type") or normalized_provider.get("provider_type")
        try:
            providers[provider_id] = LLMProviderConfig.model_validate(
                {
                    **normalized_provider,
                    "provider_type": provider_type or "openai_compatible",
                    "provider_id": provider_id,
                }
            )
        except ValidationError as exc:
            raise ValueError(f"Invalid provider config: {provider_id}") from exc

    budget_payload = (
        payload.get("budget") if isinstance(payload.get("budget"), dict) else {}
    )
    llm_payload = payload.get("llm") if isinstance(payload.get("llm"), dict) else {}

    return LLMRouterConfig(
        default_provider=str(default_provider),
        default_model=str(default_model or "fake-planner"),
        mode=str(mode),
        providers=providers,
        budget=_normalize_budget_payload(budget_payload, llm_payload=llm_payload),
    )


def default_fake_router_config() -> LLMRouterConfig:
    return LLMRouterConfig(
        default_provider="fake",
        default_model="fake-planner",
        mode="fake",
        providers={
            "fake": LLMProviderConfig(
                provider_id="fake",
                provider_type="fake",
                mode="fake",
                model="fake-planner",
            )
        },
    )


def load_llm_router_config(path: Path | None = None) -> LLMRouterConfig:
    if path is None:
        return default_fake_router_config()
    return load_llm_router_config_from_file(path)


def default_llm_config_path() -> Path | None:
    configured = os.getenv("VANISCOPE_LLM_CONFIG")
    if configured:
        path = Path(configured)
        return path if path.exists() else None
    default_path = Path("configs/llm.local.toml")
    return default_path if default_path.exists() else None


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

    if provider.provider_type in {"fake", "mock"}:
        return provider.model_copy(
            update={
                "model": model_override or provider.model or router_config.default_model,
                "mode": provider.mode or router_config.mode,
            }
        )

    if router_config.mode not in {"real", "openai_compatible"}:
        raise ValueError(
            "Real LLM provider requires router.mode = \"real\" in the LLM config."
        )

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
    if provider.provider_type in {"fake", "mock"}:
        return LLMClientConfig(
            provider=provider.provider_type,
            base_url=provider.base_url,
            api_key=provider.api_key or "",
            model=provider.model,
            fallback_model=provider.fallback_model,
            timeout_ms=provider.timeout_ms,
            temperature=provider.temperature,
            max_tokens=provider.max_tokens,
            extra_headers=provider.extra_headers,
        )
    if not provider.api_key:
        raise ValueError(f"Missing API key for LLM provider: {provider.provider_id}")
    return LLMClientConfig(
        provider=provider.provider_type,
        base_url=provider.base_url,
        api_key=provider.api_key,
        model=provider.model,
        fallback_model=provider.fallback_model,
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


def _normalize_provider_payload(payload: dict) -> dict:
    normalized = dict(payload)
    timeout_seconds = normalized.pop("timeout_seconds", None)
    if timeout_seconds is not None and "timeout_ms" not in normalized:
        try:
            normalized["timeout_ms"] = int(float(timeout_seconds) * 1000)
        except (TypeError, ValueError):
            normalized["timeout_ms"] = timeout_seconds
    return normalized


def _normalize_budget_payload(payload: dict, *, llm_payload: dict | None = None) -> dict:
    aliases = {
        "max_calls_per_task": "max_llm_calls_per_task",
        "max_prompt_tokens_per_call": "max_prompt_tokens_per_call",
        "max_input_tokens_per_task": "max_prompt_tokens",
        "max_output_tokens_per_task": "max_completion_tokens",
        "max_completion_tokens_per_call": "max_completion_tokens_per_call",
        "max_cost_usd_per_task": "max_cost_usd",
        "max_retries_per_call": "max_llm_retries_per_call",
        "retry_on_timeout": "retry_on_llm_timeout",
    }
    normalized = dict(payload)
    if llm_payload:
        for source in ("max_retries_per_call", "retry_on_timeout"):
            if source in llm_payload and source not in normalized:
                normalized[source] = llm_payload[source]
    for source, target in aliases.items():
        if source in normalized:
            normalized[target] = normalized[source]
    if "max_prompt_tokens_per_call" in normalized and "max_prompt_tokens" not in normalized:
        normalized["max_prompt_tokens"] = normalized["max_prompt_tokens_per_call"]
    if (
        "approval_prompt_tokens_per_task" in normalized
        and "max_total_tokens_per_task" not in normalized
    ):
        normalized["max_total_tokens_per_task"] = normalized[
            "approval_prompt_tokens_per_task"
        ]
    if "max_completion_tokens_per_call" in normalized and "max_completion_tokens" not in normalized:
        normalized["max_completion_tokens"] = normalized[
            "max_completion_tokens_per_call"
        ]
    return normalized
