from __future__ import annotations

from webscoper.schemas.tool import ExecutionPlan, PlannedStep
from webscoper.schemas.task import TaskSpec
from webscoper.schemas.tool import ToolCall

SUPPORTED_PLANNER_MODES = {"deterministic", "fake", "fake_llm", "llm", "real_llm"}
PLANNER_MODE_ALIASES = {
    "fake": "fake_llm",
    "llm": "real_llm",
}


class DeterministicTaskPlanner:
    def build_plan(self, task: TaskSpec) -> ExecutionPlan:
        steps = [
            PlannedStep(
                step_id="step_001",
                tool_call=ToolCall(
                    call_id="call_001",
                    tool_id="browser_open_observe",
                    arguments={"url": task.target_url},
                    reason="Open the target page and collect the initial observation.",
                ),
                reason="Open the target page and collect the initial observation.",
                expected_outcome="The target page is visible and observed.",
            )
        ]

        if task.mode == "auto_explore":
            return ExecutionPlan(
                plan_id=f"auto_explore_seed_{task.task_id}",
                task_id=task.task_id,
                steps=steps,
            )

        if task.action is None:
            steps.extend(
                [
                    PlannedStep(
                        step_id="step_002",
                        tool_call=ToolCall(
                            call_id="call_002",
                            tool_id="browser_extract",
                            reason="Extract visible page information after opening.",
                        ),
                        reason="Extract visible page information after opening.",
                        expected_outcome="Visible page information is available.",
                    ),
                    PlannedStep(
                        step_id="step_003",
                        tool_call=ToolCall(
                            call_id="call_003",
                            tool_id="finish_task",
                            arguments={
                                "summary": "Open-only browser task completed.",
                            },
                            reason="Finish the open-only browser task.",
                        ),
                        reason="Finish the open-only browser task.",
                        expected_outcome="The task is marked complete.",
                    ),
                ]
            )
        else:
            steps.extend(
                [
                    PlannedStep(
                        step_id="step_002",
                        tool_call=ToolCall(
                            call_id="call_002",
                            tool_id="browser_click_intent",
                            arguments={
                                "action": task.action.model_dump(mode="json"),
                            },
                            reason="Click the requested target and verify the expected effect.",
                        ),
                        reason="Click the requested target and verify the expected effect.",
                        expected_outcome="The requested click effect is verified.",
                    ),
                    PlannedStep(
                        step_id="step_003",
                        tool_call=ToolCall(
                            call_id="call_003",
                            tool_id="browser_extract",
                            reason="Extract visible page information after clicking.",
                        ),
                        reason="Extract visible page information after clicking.",
                        expected_outcome="Visible post-click page information is available.",
                    ),
                    PlannedStep(
                        step_id="step_004",
                        tool_call=ToolCall(
                            call_id="call_004",
                            tool_id="finish_task",
                            arguments={
                                "summary": "Click-intent browser task completed.",
                            },
                            reason="Finish the click-intent browser task.",
                        ),
                        reason="Finish the click-intent browser task.",
                        expected_outcome="The task is marked complete.",
                    ),
                ]
            )

        return ExecutionPlan(
            plan_id=f"plan_{task.task_id}",
            task_id=task.task_id,
            steps=steps,
        )


def normalize_planner_mode(mode: str | None) -> str:
    normalized = (mode or "deterministic").strip().lower()
    if normalized not in SUPPORTED_PLANNER_MODES:
        supported = ", ".join(sorted(SUPPORTED_PLANNER_MODES))
        raise ValueError(
            f"Unsupported planner mode: {mode}. Supported modes: {supported}."
        )
    return PLANNER_MODE_ALIASES.get(normalized, normalized)
