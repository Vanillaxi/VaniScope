from __future__ import annotations

from pathlib import Path

import pytest

from webscoper.eval.planner_eval import PlannerEvalRunner


@pytest.mark.asyncio
async def test_planner_eval_runner_scores_fixture_cases(tmp_path: Path) -> None:
    summary = await PlannerEvalRunner(
        cases_path=Path("tests/fixtures/planner_eval_cases.json"),
        output_root=tmp_path,
    ).run()

    run_dir = tmp_path / summary.run_id
    case_ids = {result.case_id for result in summary.results}

    assert summary.total_cases >= 8
    assert summary.passed_cases == summary.total_cases
    assert summary.success_rate == 1.0
    assert summary.parse_success_cases >= 1
    assert summary.validation_success_cases >= 1
    assert summary.repair_used_cases >= 1
    assert (run_dir / "score.json").exists()
    assert (run_dir / "report.md").exists()
    assert "invalid_json_repaired" in case_ids
    assert "unknown_tool_failed" in case_ids
    assert "lazy_tool_failed" in case_ids
    assert "click_before_open_failed" in case_ids
