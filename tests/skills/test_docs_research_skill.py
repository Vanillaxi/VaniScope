from pathlib import Path

from webscoper.runtime.execution.handler import WebAgentExecutionHandler
from webscoper.runtime.execution.runner import build_task_spec
from webscoper.workflows.langgraph_adapter import LangGraphWorkflowAdapter


def test_docs_research_skill_generates_report_and_result(tmp_path: Path) -> None:
    task = build_task_spec(
        url="tests/fixtures/mock_site/docs_research.html",
        task_type="docs_research",
        skill_id="docs_research",
        query="How do I install and run VaniScope?",
        expect="installation steps with evidence",
        language="en",
        task_id="docs_research_test",
    )
    handler = WebAgentExecutionHandler(
        output_root=tmp_path,
        workspace=Path("tests/fixtures/workspace"),
    )

    result = LangGraphWorkflowAdapter(handler).run(task)
    assert result.run_dir is not None
    run_dir = Path(result.run_dir)

    assert result.status == "succeeded"
    assert (run_dir / "final_report.md").exists()
    assert (run_dir / "evidence.jsonl").exists()
    assert (run_dir / "review.json").exists()
    assert (run_dir / "skill_result.json").exists()
    assert "uv sync" in (run_dir / "final_report.md").read_text(encoding="utf-8")
    assert "docs_research" in (run_dir / "skill_result.json").read_text(
        encoding="utf-8"
    )
