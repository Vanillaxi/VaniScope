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


class WorkflowEvalRequest(BaseModel):
    url: str
    click: str | None = None
    expect: str | None = None
    planner: str = "deterministic"
    reviewer: str = "deterministic"
    revise_attempts: int = 0
    workspace: str | None = None
    reminder: str | None = None
    repair_attempts: int = 0


class WorkflowEvalExpected(BaseModel):
    status: str | None = None
    required_artifacts: list[str] = Field(default_factory=list)
    review_passed: bool | None = None
    min_review_score: float | None = None
    expected_event_kinds: list[str] = Field(default_factory=list)
    expected_risk_status: str | None = None
    allow_backend_differences: list[str] = Field(default_factory=list)


class WorkflowEvalCase(BaseModel):
    case_id: str
    description: str
    request: WorkflowEvalRequest
    expected: WorkflowEvalExpected = Field(default_factory=WorkflowEvalExpected)


class WorkflowBackendRunResult(BaseModel):
    backend: str
    task_id: str | None = None
    status: str
    run_dir: str | None = None
    artifacts: list[str] = Field(default_factory=list)
    review_passed: bool | None = None
    review_score: float | None = None
    event_kinds: list[str] = Field(default_factory=list)
    error: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class WorkflowComparisonResult(BaseModel):
    case_id: str
    passed: bool
    native: WorkflowBackendRunResult
    langgraph: WorkflowBackendRunResult
    differences: list[str] = Field(default_factory=list)
    missing_artifacts: dict[str, list[str]] = Field(default_factory=dict)
    summary: str


class WorkflowEvalSummary(BaseModel):
    total: int
    passed: int
    failed: int
    pass_rate: float
    case_results: list[WorkflowComparisonResult] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
