from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


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
