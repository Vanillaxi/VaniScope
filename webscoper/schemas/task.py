from __future__ import annotations

from pydantic import BaseModel, Field

from webscoper.schemas.browser import ActionContract, ExpectedEffect
from webscoper.schemas.runtime import BudgetContext, SafetyContext


class TaskSpec(BaseModel):
    task_id: str
    raw_input: str
    task_type: str = "browser_task"
    mode: str = "guided"
    skill_id: str | None = None
    target_url: str
    goal: str | None = None
    query: str | None = None
    research_goal: str | None = None
    expected_output: str | None = None
    constraints: list[str] = Field(default_factory=list)
    language: str = "auto"
    action: ActionContract | None = None
    expected_effect: ExpectedEffect | None = None
    require_evidence: bool = True
    budget: BudgetContext = Field(default_factory=BudgetContext)
    safety: SafetyContext = Field(default_factory=SafetyContext)
    tags: list[str] = Field(default_factory=list)
