from __future__ import annotations

from webscoper.schemas.runtime import WebAgentContextSnapshot
from webscoper.schemas.tool import ExecutionPlan, PlannedStep
from webscoper.schemas.tool import (
    PlanValidationIssue,
    PlanValidationResult,
)
from webscoper.tools.registry import ToolRegistry
from webscoper.tools.gateway import ToolGateway


class PlanValidator:
    def __init__(
        self,
        tool_registry: ToolRegistry,
        tool_gateway: ToolGateway | None = None,
    ) -> None:
        self.tool_registry = tool_registry
        self.tool_gateway = tool_gateway

    def validate(
        self,
        plan: ExecutionPlan,
        context: WebAgentContextSnapshot,
    ) -> PlanValidationResult:
        issues: list[PlanValidationIssue] = []

        if not plan.steps:
            issues.append(
                PlanValidationIssue(
                    issue_type="EMPTY_PLAN",
                    message="Execution plan must contain at least one step.",
                )
            )

        if len(plan.steps) > context.task.budget.max_steps:
            issues.append(
                PlanValidationIssue(
                    issue_type="MAX_STEPS_EXCEEDED",
                    message=(
                        "Execution plan exceeds task budget max_steps "
                        f"({len(plan.steps)} > {context.task.budget.max_steps})."
                    ),
                )
            )

        opened = False
        browser_action_seen = False
        for index, step in enumerate(plan.steps):
            tool_id = step.tool_call.tool_id
            _validate_tool_metadata(
                step,
                context,
                self.tool_registry,
                self.tool_gateway,
                issues,
            )
            _validate_required_arguments(step, issues)

            if tool_id in _BROWSER_TOOL_IDS:
                if not browser_action_seen and tool_id != "browser_open_observe":
                    issues.append(
                        PlanValidationIssue(
                            issue_type="INVALID_TOOL_ORDER",
                            message="The first browser action must be browser_open_observe.",
                            step_id=step.step_id,
                            tool_id=tool_id,
                        )
                    )
                browser_action_seen = True

            if tool_id == "browser_open_observe":
                opened = True
            elif tool_id in {"browser_click_intent", "browser_extract"} and not opened:
                issues.append(
                    PlanValidationIssue(
                        issue_type="INVALID_TOOL_ORDER",
                        message=f"{tool_id} cannot run before browser_open_observe.",
                        step_id=step.step_id,
                        tool_id=tool_id,
                    )
                )

            if tool_id == "finish_task" and index != len(plan.steps) - 1:
                issues.append(
                    PlanValidationIssue(
                        issue_type="INVALID_TOOL_ORDER",
                        message="finish_task must be the last step.",
                        step_id=step.step_id,
                        tool_id=tool_id,
                    )
                )

        return PlanValidationResult(
            status="failed" if issues else "success",
            issues=issues,
        )


def _validate_tool_metadata(
    step: PlannedStep,
    context: WebAgentContextSnapshot,
    tool_registry: ToolRegistry,
    tool_gateway: ToolGateway | None,
    issues: list[PlanValidationIssue],
) -> None:
    tool_id = step.tool_call.tool_id
    tool = tool_registry.get(tool_id)
    if tool is None:
        if tool_gateway is not None:
            return
        issues.append(
            PlanValidationIssue(
                issue_type="UNKNOWN_TOOL",
                message=f"Unknown tool: {tool_id}.",
                step_id=step.step_id,
                tool_id=tool_id,
            )
        )
        return

    if tool_gateway is not None:
        try:
            tool_gateway.get_tool(tool_id)
            return
        except KeyError:
            pass

    if tool.loading_mode == "lazy":
        issues.append(
            PlanValidationIssue(
                issue_type="LAZY_TOOL_NOT_EXECUTABLE",
                message=f"Lazy tool {tool_id} is not executable in this phase.",
                step_id=step.step_id,
                tool_id=tool_id,
            )
        )
    elif tool.loading_mode == "runtime":
        issues.append(
            PlanValidationIssue(
                issue_type="UNSUPPORTED_TOOL_TYPE",
                message=f"Runtime-loaded tool {tool_id} is not executable in this phase.",
                step_id=step.step_id,
                tool_id=tool_id,
            )
        )

    if tool.tool_type != "local":
        issues.append(
            PlanValidationIssue(
                issue_type="UNSUPPORTED_TOOL_TYPE",
                message=f"Unsupported tool type for {tool_id}: {tool.tool_type}.",
                step_id=step.step_id,
                tool_id=tool_id,
            )
        )

    if context.safety.mode == "read_only" and tool.risk_level != "read_only":
        issues.append(
            PlanValidationIssue(
                issue_type="TOOL_BLOCKED_BY_SAFETY",
                message=f"Tool {tool_id} is blocked by read_only safety mode.",
                step_id=step.step_id,
                tool_id=tool_id,
            )
        )


def _validate_required_arguments(
    step: PlannedStep,
    issues: list[PlanValidationIssue],
) -> None:
    tool_id = step.tool_call.tool_id
    arguments = step.tool_call.arguments
    if tool_id == "browser_open_observe" and not arguments.get("url"):
        issues.append(
            PlanValidationIssue(
                issue_type="MISSING_REQUIRED_ARGUMENT",
                message="browser_open_observe requires arguments.url.",
                step_id=step.step_id,
                tool_id=tool_id,
            )
        )
    if tool_id == "browser_click_intent" and not arguments.get("action"):
        issues.append(
            PlanValidationIssue(
                issue_type="MISSING_REQUIRED_ARGUMENT",
                message="browser_click_intent requires arguments.action.",
                step_id=step.step_id,
                tool_id=tool_id,
            )
        )


_BROWSER_TOOL_IDS = {
    "browser_open_observe",
    "browser_click_intent",
    "browser_extract",
}
