from __future__ import annotations

from pydantic import BaseModel, Field

from webscoper.schemas.action import ActionContract, ExpectedEffect


class BudgetContext(BaseModel):
    max_steps: int = 10
    timeout_ms: int = 10000
    retry_limit: int = 0
    max_cost_usd: float | None = None


class SafetyContext(BaseModel):
    mode: str = "read_only"
    allow_login: bool = False
    allow_captcha_bypass: bool = False
    allow_sensitive_input: bool = False
    allow_external_submit: bool = False


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
