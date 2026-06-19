from __future__ import annotations

from pydantic import BaseModel, Field

from webscoper.schemas.browser import ActionContract, ExpectedEffect
from webscoper.schemas.runtime import BudgetContext, SafetyContext


class TaskSpec(BaseModel):
    task_id: str
    raw_input: str
    task_type: str = "browser_task"
    target_url: str
    action: ActionContract | None = None
    expected_effect: ExpectedEffect | None = None
    require_evidence: bool = True
    budget: BudgetContext = Field(default_factory=BudgetContext)
    safety: SafetyContext = Field(default_factory=SafetyContext)
    tags: list[str] = Field(default_factory=list)
