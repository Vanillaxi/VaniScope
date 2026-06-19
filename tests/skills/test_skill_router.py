from pathlib import Path

from webscoper.runtime.execution.runner import build_task_spec
from webscoper.skills.router import SkillRouter


def test_router_uses_explicit_skill_id() -> None:
    task = build_task_spec(
        url="tests/fixtures/mock_site/docs_research.html",
        skill_id="docs_research",
        query="How do I install VaniScope?",
    )

    route = SkillRouter().route(task)

    assert route.skill is not None
    assert route.task.skill_id == "docs_research"
    assert route.task.task_type == "docs_research"
    assert route.reason == "explicit_skill_id"


def test_router_uses_url_and_query_for_docs_research() -> None:
    task = build_task_spec(
        url=str(Path("tests/fixtures/mock_site/docs_research.html")),
        query="How do I install VaniScope?",
    )

    route = SkillRouter().route(task)

    assert route.skill is not None
    assert route.task.skill_id == "docs_research"
    assert route.task.task_type == "docs_research"
    assert route.reason == "url_with_query"
