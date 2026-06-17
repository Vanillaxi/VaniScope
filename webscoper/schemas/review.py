from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


ReviewSeverity = Literal["info", "warning", "error"]


class ReviewIssue(BaseModel):
    issue_id: str
    severity: ReviewSeverity
    issue_type: str
    message: str
    evidence_id: str | None = None
    location: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ClaimEvidenceCheck(BaseModel):
    claim: str
    evidence_ids: list[str] = Field(default_factory=list)
    supported: bool
    reason: str


class ReviewResult(BaseModel):
    passed: bool
    score: float
    issues: list[ReviewIssue] = Field(default_factory=list)
    claim_checks: list[ClaimEvidenceCheck] = Field(default_factory=list)
    summary: str
    metadata: dict[str, Any] = Field(default_factory=dict)
