import json
from pathlib import Path

from webscoper.runtime.execution.handler import WebAgentExecutionHandler
from webscoper.runtime.execution.runner import build_task_spec
from webscoper.workflows.langgraph_adapter import LangGraphWorkflowAdapter


def test_langgraph_prompt_and_state_include_skill_context(tmp_path: Path) -> None:
    task = build_task_spec(
        url="tests/fixtures/mock_site/docs_research.html",
        task_type="docs_research",
        skill_id="docs_research",
        query="How do I install and run VaniScope?",
        task_id="skill_integration",
    )
    handler = WebAgentExecutionHandler(
        output_root=tmp_path,
        workspace=Path("tests/fixtures/workspace"),
    )

    result = LangGraphWorkflowAdapter(handler).run(task)
    assert result.run_dir is not None
    run_dir = Path(result.run_dir)
    prompt = (run_dir / "prompt_preview.md").read_text(encoding="utf-8")
    prompt_context = json.loads((run_dir / "prompt_context.json").read_text())
    workflow_state = json.loads((run_dir / "workflow_state.json").read_text())

    assert result.status == "succeeded"
    assert "# Skill Instruction" in prompt
    assert "Do not invent details" in prompt
    assert prompt_context["skill"]["skill_id"] == "docs_research"
    assert workflow_state["skill_id"] == "docs_research"
    assert "skill_result.json" in result.artifacts
