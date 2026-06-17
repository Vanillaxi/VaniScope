from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class BrowserEvalExpected(BaseModel):
    status: str = "success"
    must_contain_text: str | None = None
    must_have_risk_type: str | None = None
    expected_error_type: str | None = None


class BrowserEvalCase(BaseModel):
    case_id: str
    description: str
    url: str
    click: str | None = None
    expect: BrowserEvalExpected
    tags: list[str] = Field(default_factory=list)


class BrowserEvalCaseResult(BaseModel):
    case_id: str
    passed: bool
    status: str
    error_type: str | None = None
    message: str | None = None
    run_dir: str | None = None
    trace_path: str | None = None
    screenshot_path: str | None = None
    metrics: dict[str, Any] = Field(default_factory=dict)


class BrowserEvalSummary(BaseModel):
    run_id: str
    total_cases: int
    passed_cases: int
    failed_cases: int
    task_success_rate: float
    recovery_attempt_count: int = 0
    recovered_case_count: int = 0
    recovery_success_rate: float = 0.0
    blocked_recovery_count: int = 0
    results: list[BrowserEvalCaseResult]


class ReviewerEvalExpected(BaseModel):
    passed: bool | None = None
    min_score: float | None = None
    max_score: float | None = None
    issue_types: list[str] = Field(default_factory=list)


class ReviewerEvalCase(BaseModel):
    case_id: str
    description: str
    report_markdown: str
    evidence_items: list[dict[str, Any]] = Field(default_factory=list)
    expected_text: str | None = None
    expected: ReviewerEvalExpected = Field(default_factory=ReviewerEvalExpected)


class ReviewerEvalCaseResult(BaseModel):
    case_id: str
    passed: bool
    reviewer_passed: bool
    score: float
    expected_passed: bool | None = None
    expected_issue_types: list[str] = Field(default_factory=list)
    actual_issue_types: list[str] = Field(default_factory=list)
    missing_issue_types: list[str] = Field(default_factory=list)
    unexpected_issue_types: list[str] = Field(default_factory=list)
    error: str | None = None


class ReviewerEvalSummary(BaseModel):
    total: int
    passed: int
    failed: int
    pass_rate: float
    average_review_score: float
    case_results: list[ReviewerEvalCaseResult] = Field(default_factory=list)
