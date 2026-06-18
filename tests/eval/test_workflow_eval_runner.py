from __future__ import annotations

import json
from pathlib import Path

from webscoper.eval.workflow_eval import (
    WorkflowRegressionEvalRunner,
    compare_workflow_backend_results,
)
from webscoper.schemas.eval import (
    WorkflowBackendRunResult,
    WorkflowComparisonResult,
    WorkflowEvalCase,
    WorkflowEvalExpected,
    WorkflowEvalRequest,
)


def test_workflow_eval_fixture_cases_load_by_type() -> None:
    cases = _fixture_cases()
    by_type = {case_type: 0 for case_type in ["workflow", "recovery", "approval"]}
    for case in cases:
        by_type[case.case_type] += 1

    assert len(cases) >= 15
    assert by_type["workflow"] >= 1
    assert by_type["recovery"] >= 7
    assert by_type["approval"] >= 5
    assert {case.case_id for case in cases} >= {
        "basic_click",
        "lazy_button_recovery",
        "modal_overlay_recovery",
        "no_effect_retry_recovery",
        "target_ambiguous_recovery",
        "disabled_button_blocked",
        "login_required_blocked",
        "captcha_detected_blocked",
        "submit_requires_approval",
        "submit_approved_resume",
        "submit_rejected_stops",
        "delete_blocked",
        "approval_state_persisted",
    }


def test_basic_click_case_passes_native_and_langgraph(tmp_path: Path) -> None:
    case = _fixture_case("basic_click")

    result = WorkflowRegressionEvalRunner(tmp_path).run_case(case)

    assert result.passed
    assert result.native.status == "succeeded"
    assert result.langgraph.status == "succeeded"
    assert result.native.review_passed is True
    assert result.langgraph.review_passed is True


def test_lazy_button_recovery_matches_native_and_langgraph(tmp_path: Path) -> None:
    result = WorkflowRegressionEvalRunner(tmp_path).run_case(
        _fixture_case("lazy_button_recovery")
    )

    assert result.passed
    assert result.case_type == "recovery"
    assert result.native.status == "succeeded"
    assert result.langgraph.status == "succeeded"
    assert "wait_and_reobserve" in result.native.recovery_kinds
    assert "wait_and_reobserve" in result.langgraph.recovery_kinds


def test_submit_requires_approval_pauses_both_backends(tmp_path: Path) -> None:
    result = WorkflowRegressionEvalRunner(tmp_path).run_case(
        _fixture_case("submit_requires_approval")
    )

    assert result.passed
    assert result.case_type == "approval"
    assert result.native.status == "requires_approval"
    assert result.langgraph.status == "requires_approval"
    assert "approval_required" in result.native.event_kinds
    assert "approval_required" in result.langgraph.event_kinds


def test_submit_approved_resume_finishes(tmp_path: Path) -> None:
    result = WorkflowRegressionEvalRunner(tmp_path).run_case(
        _fixture_case("submit_approved_resume")
    )

    assert result.passed
    assert result.native.status == "succeeded"
    assert result.langgraph.status == "succeeded"
    assert "approved" in result.native.approval_statuses
    assert "approved" in result.langgraph.approval_statuses
    assert "final_report.md" in result.native.artifacts
    assert "final_report.md" in result.langgraph.artifacts


def test_delete_blocked_does_not_enter_approval_resume(tmp_path: Path) -> None:
    result = WorkflowRegressionEvalRunner(tmp_path).run_case(_fixture_case("delete_blocked"))

    assert result.passed
    assert result.native.status == "blocked"
    assert result.langgraph.status == "blocked"
    assert result.native.metadata["approval_request_count"] == 0
    assert result.langgraph.metadata["approval_request_count"] == 0
    assert "task_resumed" not in result.native.event_kinds
    assert "task_resumed" not in result.langgraph.event_kinds


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


def test_single_case_failure_does_not_interrupt_eval(tmp_path: Path, monkeypatch) -> None:
    cases = [
        _case(case_id="synthetic_fail"),
        _case(case_id="synthetic_pass"),
    ]
    outcomes = iter(
        [
            _comparison("synthetic_fail", passed=False, difference="synthetic failure"),
            _comparison("synthetic_pass", passed=True),
        ]
    )
    monkeypatch.setattr(
        WorkflowRegressionEvalRunner,
        "run_case",
        lambda _self, _case: next(outcomes),
    )

    summary = WorkflowRegressionEvalRunner(tmp_path).run_cases(cases)

    assert summary.total == 2
    assert summary.passed == 1
    assert summary.failed == 1
    assert summary.case_results[0].differences == ["synthetic failure"]
    assert summary.case_results[1].passed


def test_real_llm_is_rejected_for_offline_eval(tmp_path: Path) -> None:
    cases = [_case(case_id="real_llm_guard", planner="real_llm")]

    summary = WorkflowRegressionEvalRunner(tmp_path).run_cases(cases)

    assert summary.failed == 1
    assert "real_llm" in (summary.case_results[0].native.error or "")


def test_score_and_report_are_generated(tmp_path: Path, monkeypatch) -> None:
    case = _case(case_id="synthetic_score")
    monkeypatch.setattr(
        WorkflowRegressionEvalRunner,
        "run_case",
        lambda _self, _case: _comparison("synthetic_score", passed=True),
    )

    summary = WorkflowRegressionEvalRunner(tmp_path).run_cases([case])

    score_payload = json.loads((tmp_path / "score.json").read_text(encoding="utf-8"))
    report = (tmp_path / "report.md").read_text(encoding="utf-8")
    assert score_payload["total"] == summary.total
    assert score_payload["total_cases"] == summary.total
    assert "recovery_cases_passed" in score_payload
    assert "approval_cases_passed" in score_payload
    assert "# VaniScope Workflow Regression Eval Report" in report
    assert "synthetic_score" in report


def _fixture_cases() -> list[WorkflowEvalCase]:
    return [
        WorkflowEvalCase.model_validate(item)
        for item in json.loads(
            Path("tests/fixtures/workflow_eval_cases.json").read_text(encoding="utf-8")
        )
    ]


def _fixture_case(case_id: str) -> WorkflowEvalCase:
    for item in _fixture_cases():
        if item.case_id == case_id:
            return item
    raise AssertionError(f"Missing fixture case: {case_id}")


def _case(
    case_id: str = "case",
    status: str | None = "succeeded",
    required_artifacts: list[str] | None = None,
    allow_backend_differences: list[str] | None = None,
    url: str = "tests/fixtures/mock_site/basic.html",
    planner: str = "deterministic",
) -> WorkflowEvalCase:
    return WorkflowEvalCase(
        case_id=case_id,
        description="Synthetic workflow comparison case.",
        request=WorkflowEvalRequest(url=url, planner=planner),
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


def _comparison(
    case_id: str,
    passed: bool,
    difference: str | None = None,
) -> WorkflowComparisonResult:
    differences = [difference] if difference else []
    return WorkflowComparisonResult(
        case_id=case_id,
        passed=passed,
        native=_result("native"),
        langgraph=_result("langgraph"),
        differences=differences,
        summary="Backends matched expectations." if passed else "; ".join(differences),
    )
