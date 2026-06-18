from __future__ import annotations

import json
from pathlib import Path

from webscoper.eval.workflow_eval import (
    WorkflowRegressionEvalRunner,
    compare_workflow_backend_results,
)
from webscoper.schemas.eval import (
    WorkflowBackendRunResult,
    WorkflowEvalCase,
    WorkflowEvalExpected,
    WorkflowEvalRequest,
)


def test_workflow_eval_runner_loads_fixture_cases(tmp_path: Path) -> None:
    summary = WorkflowRegressionEvalRunner(tmp_path).run_file(
        Path("tests/fixtures/workflow_eval_cases.json")
    )

    assert summary.total >= 8
    assert (tmp_path / "score.json").exists()
    assert (tmp_path / "report.md").exists()


def test_basic_click_case_passes_native_and_langgraph(tmp_path: Path) -> None:
    case = _fixture_case("basic_click")

    result = WorkflowRegressionEvalRunner(tmp_path).run_case(case)

    assert result.passed
    assert result.native.status == "succeeded"
    assert result.langgraph.status == "succeeded"
    assert result.native.review_passed is True
    assert result.langgraph.review_passed is True


def test_required_artifacts_missing_fails_case() -> None:
    case = _case(required_artifacts=["final_report.md"])
    native = _result("native", artifacts=[])
    langgraph = _result("langgraph", artifacts=["final_report.md"])

    result = compare_workflow_backend_results(case, native, langgraph)

    assert not result.passed
    assert result.missing_artifacts == {"native": ["final_report.md"]}


def test_status_mismatch_fails_case() -> None:
    case = _case(status=None)
    native = _result("native", status="succeeded")
    langgraph = _result("langgraph", status="blocked")

    result = compare_workflow_backend_results(case, native, langgraph)

    assert not result.passed
    assert "status differs" in result.differences[0]


def test_allow_backend_differences_can_ignore_allowed_status_difference() -> None:
    case = _case(
        status=None,
        allow_backend_differences=["status"],
    )
    native = _result("native", status="succeeded")
    langgraph = _result("langgraph", status="blocked")

    result = compare_workflow_backend_results(case, native, langgraph)

    assert result.passed


def test_single_case_failure_does_not_interrupt_eval(tmp_path: Path) -> None:
    cases = [
        _case(case_id="offline_guard", url="https://example.com"),
        _fixture_case("basic_click"),
    ]

    summary = WorkflowRegressionEvalRunner(tmp_path).run_cases(cases)

    assert summary.total == 2
    assert summary.passed == 1
    assert summary.failed == 1
    assert summary.case_results[0].native.error is not None
    assert summary.case_results[1].passed


def test_score_and_report_are_generated(tmp_path: Path) -> None:
    case = _fixture_case("basic_click")

    summary = WorkflowRegressionEvalRunner(tmp_path).run_cases([case])

    score_payload = json.loads((tmp_path / "score.json").read_text(encoding="utf-8"))
    report = (tmp_path / "report.md").read_text(encoding="utf-8")
    assert score_payload["total"] == summary.total
    assert "# VaniScope Workflow Regression Eval Report" in report
    assert "basic_click" in report


def _fixture_case(case_id: str) -> WorkflowEvalCase:
    payload = json.loads(
        Path("tests/fixtures/workflow_eval_cases.json").read_text(encoding="utf-8")
    )
    for item in payload:
        if item["case_id"] == case_id:
            return WorkflowEvalCase.model_validate(item)
    raise AssertionError(f"Missing fixture case: {case_id}")


def _case(
    case_id: str = "case",
    status: str | None = "succeeded",
    required_artifacts: list[str] | None = None,
    allow_backend_differences: list[str] | None = None,
    url: str = "tests/fixtures/mock_site/basic.html",
) -> WorkflowEvalCase:
    return WorkflowEvalCase(
        case_id=case_id,
        description="Synthetic workflow comparison case.",
        request=WorkflowEvalRequest(url=url),
        expected=WorkflowEvalExpected(
            status=status,
            required_artifacts=required_artifacts or [],
            allow_backend_differences=allow_backend_differences or [],
        ),
    )


def _result(
    backend: str,
    status: str = "succeeded",
    artifacts: list[str] | None = None,
) -> WorkflowBackendRunResult:
    return WorkflowBackendRunResult(
        backend=backend,
        task_id=f"{backend}_task",
        status=status,
        artifacts=artifacts or [],
        event_kinds=[],
    )
