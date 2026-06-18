from __future__ import annotations

from webscoper.runtime.planner import DeterministicTaskPlanner
from webscoper.schemas.action import ActionContract, ExpectedEffect
from webscoper.schemas.task import TaskSpec


def test_deterministic_planner_builds_open_only_plan() -> None:
    task = TaskSpec(
        task_id="open_task",
        raw_input="Open a page.",
        target_url="file:///tmp/basic.html",
    )

    plan = DeterministicTaskPlanner().build_plan(task)
    tool_ids = [step.tool_call.tool_id for step in plan.steps]

    assert tool_ids == ["browser_open_observe", "browser_extract", "finish_task"]


def test_deterministic_planner_builds_click_plan() -> None:
    action = ActionContract(
        action_type="click",
        intent="Click Quickstart",
        target_hint="Quickstart",
        preferred_roles=["button", "link"],
        preconditions=["target_visible", "target_enabled"],
        expected_effect=ExpectedEffect(
            type="content_appears",
            value="pip install playwright",
        ),
        risk_level="read_only",
    )
    task = TaskSpec(
        task_id="click_task",
        raw_input="Click Quickstart.",
        target_url="file:///tmp/basic.html",
        action=action,
    )

    plan = DeterministicTaskPlanner().build_plan(task)
    tool_ids = [step.tool_call.tool_id for step in plan.steps]

    assert tool_ids == [
        "browser_open_observe",
        "browser_click_intent",
        "browser_extract",
        "finish_task",
    ]
