from __future__ import annotations

from pydantic import BaseModel, Field


class ToolSpec(BaseModel):
    tool_id: str
    name: str
    description: str
    prompt: str
    tool_type: str = "local"
    loading_mode: str = "core"
    permission: str = "read_only"
    risk_level: str = "read_only"
    timeout_ms: int = 5000
    schema_summary: dict[str, str] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)


class ToolSearchResult(BaseModel):
    query: str
    matches: list[ToolSpec] = Field(default_factory=list)


class ToolCatalogSnapshot(BaseModel):
    core_tools: list[ToolSpec] = Field(default_factory=list)
    lazy_tools: list[ToolSpec] = Field(default_factory=list)
    runtime_tools: list[ToolSpec] = Field(default_factory=list)
