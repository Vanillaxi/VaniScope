from __future__ import annotations

from typing import Literal, Protocol

from pydantic import BaseModel, Field


SkillStatus = Literal["planned", "success", "failed", "insufficient_info"]


class SkillInstruction(BaseModel):
    title: str
    content: str


class SkillDefinition(BaseModel):
    skill_id: str
    name: str
    description: str
    version: str
    supported_task_types: list[str] = Field(default_factory=list)
    required_tools: list[str] = Field(default_factory=list)
    risk_level: str = "safe"
    instruction: SkillInstruction


class SkillInput(BaseModel):
    raw_task: str
    url: str | None = None
    query: str | None = None
    expected_output: str | None = None
    constraints: list[str] = Field(default_factory=list)
    language: str = "auto"


class SkillPlan(BaseModel):
    skill_id: str
    objective: str
    steps: list[str] = Field(default_factory=list)
    required_evidence: list[str] = Field(default_factory=list)
    expected_artifacts: list[str] = Field(default_factory=list)


class SkillResult(BaseModel):
    skill_id: str
    status: SkillStatus
    summary: str
    evidence_ids: list[str] = Field(default_factory=list)
    artifact_names: list[str] = Field(default_factory=list)
    metadata: dict[str, object] = Field(default_factory=dict)


class Skill(Protocol):
    definition: SkillDefinition

    def build_input(self, task: object) -> SkillInput:
        ...

    def plan(self, skill_input: SkillInput) -> SkillPlan:
        ...
