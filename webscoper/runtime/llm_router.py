from __future__ import annotations

from pathlib import Path

from webscoper.runtime.llm_client import BaseLLMClient, OpenAICompatibleLLMClient
from webscoper.runtime.llm_config import (
    load_llm_router_config_from_file,
    provider_config_to_client_config,
    resolve_llm_provider_config,
)


class LLMProviderRouter:
    def __init__(self, config_path: Path) -> None:
        self.config_path = config_path
        self.router_config = load_llm_router_config_from_file(config_path)

    def create_client(
        self,
        provider_id: str | None = None,
        model_override: str | None = None,
    ) -> BaseLLMClient:
        provider = resolve_llm_provider_config(
            self.router_config,
            provider_id=provider_id,
            model_override=model_override,
        )
        if provider.provider_type == "openai_compatible":
            return OpenAICompatibleLLMClient(provider_config_to_client_config(provider))
        raise ValueError(
            f"Unsupported LLM provider_type for {provider.provider_id}: "
            f"{provider.provider_type}"
        )
