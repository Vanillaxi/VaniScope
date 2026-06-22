from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


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
    expected_skill_id: str | None = None
    skill_status: str | None = None
    require_affected_modules: bool = False
    require_difficulty: bool = False
    require_contribution_value: bool = False


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


BenchmarkSiteType = Literal["local_fixture", "public_web", "benchmark"]
BenchmarkCriterionType = Literal[
    "content_appears",
    "url_contains",
    "extracted_field_equals",
    "report_contains",
    "evidence_exists",
]


class BrowserBenchmarkSuccessCriterion(BaseModel):
    type: BenchmarkCriterionType
    value: str
    field: str | None = None


class BrowserBenchmarkEvalCase(BaseModel):
    case_id: str
    site_type: BenchmarkSiteType = "local_fixture"
    start_url: str
    goal: str
    allowed_domains: list[str] = Field(default_factory=list)
    max_steps: int = 5
    success_criteria: list[BrowserBenchmarkSuccessCriterion] = Field(default_factory=list)
    risk_policy: str = "read_only"


class BrowserBenchmarkMetrics(BaseModel):
    task_success_rate: float = 0.0
    step_success_rate: float = 0.0
    avg_steps: float = 0.0
    recovery_rate: float = 0.0
    unsafe_action_block_rate: float = 0.0
    evidence_completeness: float = 0.0
    screenshot_evidence_rate: float = 0.0
    graph_artifact_rate: float = 0.0
    report_quality_basic: float = 0.0
