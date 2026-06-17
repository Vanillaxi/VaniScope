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
    results: list[BrowserEvalCaseResult]
