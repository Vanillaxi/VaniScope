from __future__ import annotations

import json
from pathlib import Path

from webscoper.eval.workflow_eval import WorkflowRegressionEvalRunner
from webscoper.schemas.eval import WorkflowEvalCase


def test_tool_gateway_eval_fixture_cases_are_langgraph_first() -> None:
    cases = _fixture_cases()

    assert len(cases) == 8
    assert {case.case_type for case in cases} == {"tool_gateway"}
    assert {case.case_id for case in cases} == {
        "langgraph_gateway_browser_click",
        "langgraph_gateway_fake_mcp_echo",
        "langgraph_gateway_tool_search_lazy",
        "langgraph_gateway_sensitive_requires_approval",
        "langgraph_gateway_dangerous_blocked",
        "langgraph_gateway_unknown_tool_blocked",
        "langgraph_gateway_disabled_tool_blocked",
        "langgraph_gateway_audit_written",
    }


def test_tool_gateway_eval_cases_pass_and_write_langgraph_audit(tmp_path: Path) -> None:
    cases = _fixture_cases()

    summary = WorkflowRegressionEvalRunner(tmp_path).run_cases(cases)

    assert summary.total == 8
    assert summary.passed == 8
    assert summary.failed == 0
    for result in summary.case_results:
        assert result.result.status in {"succeeded", "requires_approval", "blocked"}
        run_dir = Path(result.result.run_dir or "")
        audit_rows = _read_jsonl(run_dir / "tool_audit.jsonl")
        assert audit_rows
        assert all(row["workflow_backend"] == "langgraph" for row in audit_rows)
        assert {
            "timestamp",
            "task_id",
            "workflow_backend",
            "tool_name",
            "provider_type",
            "permission",
            "risk_level",
            "decision",
            "status",
            "error_type",
            "duration_ms",
            "approval_id",
        } <= set(audit_rows[-1])


def _fixture_cases() -> list[WorkflowEvalCase]:
    payload = json.loads(
        Path("tests/fixtures/tool_gateway_eval_cases.json").read_text(encoding="utf-8")
    )
    return [WorkflowEvalCase.model_validate(item) for item in payload]


def _read_jsonl(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
