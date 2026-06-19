from __future__ import annotations

from typing import Any, Literal

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
    task_type: str = "browser_task"
    skill_id: str | None = None
    query: str | None = None
    research_goal: str | None = None
    language: str = "auto"
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)
    planner: str = "deterministic"
    reviewer: str = "deterministic"
    revise_attempts: int = 0
    workspace: str | None = None
    reminder: str | None = None
    repair_attempts: int = 0


class WorkflowEvalExpected(BaseModel):
    status: str | None = None
    expected_status: str | None = None
    required_artifacts: list[str] = Field(default_factory=list)
    expected_artifacts: list[str] = Field(default_factory=list)
    review_passed: bool | None = None
    min_review_score: float | None = None
    expected_event_kinds: list[str] = Field(default_factory=list)
    expected_recovery_kinds: list[str] = Field(default_factory=list)
    expected_recovery_error_type: str | None = None
    expected_approval_events: list[str] = Field(default_factory=list)
    expected_risk_status: str | None = None
    expected_risk_decision: str | None = None
    simulate_approval_decision: Literal["approved", "rejected"] | None = None
    final_report_contains: list[str] = Field(default_factory=list)
    min_evidence_count: int | None = None
    skill_status: str | None = None


class WorkflowEvalCase(BaseModel):
    case_id: str
    description: str
    case_type: Literal["workflow", "recovery", "approval", "tool_gateway"] = "workflow"
    request: WorkflowEvalRequest
    expected: WorkflowEvalExpected = Field(default_factory=WorkflowEvalExpected)


class WorkflowEvalRunResult(BaseModel):
    task_id: str | None = None
    status: str
    run_dir: str | None = None
    artifacts: list[str] = Field(default_factory=list)
    review_passed: bool | None = None
    review_score: float | None = None
    event_kinds: list[str] = Field(default_factory=list)
    recovery_kinds: list[str] = Field(default_factory=list)
    recovery_error_types: list[str] = Field(default_factory=list)
    approval_statuses: list[str] = Field(default_factory=list)
    error: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class WorkflowEvalCaseResult(BaseModel):
    case_id: str
    case_type: Literal["workflow", "recovery", "approval", "tool_gateway"] = "workflow"
    passed: bool
    result: WorkflowEvalRunResult
    differences: list[str] = Field(default_factory=list)
    missing_artifacts: list[str] = Field(default_factory=list)
    summary: str


class WorkflowEvalSummary(BaseModel):
    total: int
    passed: int
    failed: int
    pass_rate: float
    total_cases: int
    passed_cases: int
    failed_cases: int
    recovery_cases_passed: int = 0
    approval_cases_passed: int = 0
    langgraph_failures: int = 0
    expectation_failures: int = 0
    case_results: list[WorkflowEvalCaseResult] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class PlannerEvalCase(BaseModel):
    case_id: str
    description: str
    raw_input: str
    target_url: str
    click: str | None = None
    expect_text: str | None = None

    llm_output: str
    repair_output: str | None = None
    repair_attempts: int = 0

    expected_status: str = "success"
    expected_error_type: str | None = None
    expected_tool_ids: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)


class PlannerEvalCaseResult(BaseModel):
    case_id: str
    passed: bool
    status: str
    error_type: str | None = None
    message: str | None = None
    parsed_tool_ids: list[str] = Field(default_factory=list)
    validation_status: str | None = None
    validation_issues: list[dict[str, Any]] = Field(default_factory=list)
    repair_used: bool = False


class PlannerEvalSummary(BaseModel):
    run_id: str
    total_cases: int
    passed_cases: int
    failed_cases: int
    success_rate: float
    parse_success_cases: int
    validation_success_cases: int
    repair_used_cases: int
    results: list[PlannerEvalCaseResult] = Field(default_factory=list)
