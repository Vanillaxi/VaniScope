import json
from pathlib import Path

from webscoper.eval.workflow_eval import WorkflowRegressionEvalRunner
from webscoper.schemas.eval import WorkflowEvalCase


def test_langgraph_skill_eval_fixture_cases_pass(tmp_path: Path) -> None:
    cases = [
        WorkflowEvalCase.model_validate(item)
        for item in json.loads(
            Path("tests/fixtures/langgraph_skill_eval_cases.json").read_text(
                encoding="utf-8"
            )
        )
    ]

    summary = WorkflowRegressionEvalRunner(tmp_path).run_cases(cases)

    assert summary.total == 4
    assert summary.failed == 0
