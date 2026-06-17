from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from webscoper.schemas.tool_call import ToolCall


class LLMMessage(BaseModel):
    role: str
    content: str


class LLMRequest(BaseModel):
    messages: list[LLMMessage] = Field(default_factory=list)
    model: str = "fake-llm"
    temperature: float = 0.0
    max_tokens: int = 2048
    metadata: dict[str, Any] = Field(default_factory=dict)


class LLMResponse(BaseModel):
    content: str
    model: str = "fake-llm"
    usage: dict[str, Any] = Field(default_factory=dict)
    raw: dict[str, Any] = Field(default_factory=dict)


class ParsedToolCalls(BaseModel):
    status: str
    tool_calls: list[ToolCall] = Field(default_factory=list)
    error_type: str | None = None
    error_message: str | None = None
    raw_text: str | None = None


class LLMClientConfig(BaseModel):
    provider: str = "openai_compatible"
    base_url: str
    api_key: str
    model: str
    timeout_ms: int = 30000
    temperature: float = 0.0
    max_tokens: int = 2048
    extra_headers: dict[str, str] = Field(default_factory=dict)


class LLMProviderConfig(BaseModel):
    provider_id: str
    enabled: bool = True
    provider_type: str = "openai_compatible"
    base_url: str
    api_key: str | None = None
    api_key_env: str | None = None
    model: str
    timeout_ms: int = 30000
    temperature: float = 0.0
    max_tokens: int = 2048
    extra_headers: dict[str, str] = Field(default_factory=dict)


class LLMRouterConfig(BaseModel):
    default_provider: str
    providers: dict[str, LLMProviderConfig] = Field(default_factory=dict)
