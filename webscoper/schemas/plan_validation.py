from __future__ import annotations

from pydantic import BaseModel, Field


class PlanValidationIssue(BaseModel):
    issue_type: str
    message: str
    step_id: str | None = None
    tool_id: str | None = None


class PlanValidationResult(BaseModel):
    status: str
    issues: list[PlanValidationIssue] = Field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.status == "success"
