from __future__ import annotations

import os

from webscoper.schemas.llm import LLMClientConfig


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
