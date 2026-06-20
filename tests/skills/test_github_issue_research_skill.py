import json
from pathlib import Path

from webscoper.runtime.execution.handler import WebAgentExecutionHandler
from webscoper.runtime.execution.runner import build_task_spec
from webscoper.workflows import LangGraphWorkflowAdapter


def test_github_issue_research_skill_generates_structured_artifacts(
    tmp_path: Path,
) -> None:
    task = build_task_spec(
        url="tests/fixtures/mock_site/github_issue_research.html",
        task_type="github_issue_research",
        skill_id="github_issue_research",
        query=(
            "Analyze whether this issue is worth doing and summarize difficulty, "
            "affected modules, and risks."
        ),
        language="en",
        task_id="github_issue_research_test",
    )
    handler = WebAgentExecutionHandler(
        output_root=tmp_path,
        workspace=Path("tests/fixtures/workspace"),
    )

    result = LangGraphWorkflowAdapter(handler).run(task)

    assert result.status == "succeeded"
    assert result.run_dir is not None
    run_dir = Path(result.run_dir)
    report = (run_dir / "final_report.md").read_text(encoding="utf-8")
    skill_result = json.loads((run_dir / "skill_result.json").read_text())
    evidence_lines = (run_dir / "evidence.jsonl").read_text(encoding="utf-8")

    assert "## Affected Modules" in report
    assert "common/url.go" in report
    assert "## Difficulty Estimate" in report
    assert skill_result["skill_id"] == "github_issue_research"
    assert skill_result["difficulty"] in {"low", "medium", "high"}
    assert skill_result["contribution_value"] in {"low", "medium", "high"}
    assert skill_result["affected_modules"]
    assert '"skill_id": "github_issue_research"' in evidence_lines
