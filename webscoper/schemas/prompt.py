from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class AgentsMdInstruction(BaseModel):
    source_path: str
    content: str


class RuntimeReminder(BaseModel):
    message: str
    level: str = "info"
    source: str = "runtime"


class PromptBuildInput(BaseModel):
    identity: str
    task_summary: str
    safety_policy: str
    permission_mode: str
    agents_md_instructions: list[AgentsMdInstruction] = Field(default_factory=list)
    runtime_reminders: list[RuntimeReminder] = Field(default_factory=list)


class PromptBuildResult(BaseModel):
    prompt_text: str
    sections: dict[str, str] = Field(default_factory=dict)
    loaded_agents_md_paths: list[str] = Field(default_factory=list)
    core_tool_ids: list[str] = Field(default_factory=list)
    lazy_tool_ids: list[str] = Field(default_factory=list)
    compact_context_metadata: dict[str, Any] | None = None
