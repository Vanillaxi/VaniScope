from __future__ import annotations

import json
import re
from typing import Any

from webscoper.schemas.llm import ParsedToolCalls
from webscoper.schemas.runtime import WebAgentContextSnapshot
from webscoper.schemas.tool import (
    ExecutionPlan,
    PlanValidationIssue,
    PlanValidationResult,
    PlannedStep,
)
from webscoper.schemas.task import TaskSpec
from webscoper.schemas.tool import ToolCall
from webscoper.tools.gateway import ToolGateway
from webscoper.tools.registry import ToolRegistry

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
                    tool_id="browser_open",
                    arguments={"url": task.target_url},
                    reason="Open the target page.",
                ),
                reason="Open the target page.",
                expected_outcome="The target page is visible.",
            ),
            PlannedStep(
                step_id="step_002",
                tool_call=ToolCall(
                    call_id="call_002",
                    tool_id="browser_observe",
                    arguments={"include_screenshot": True},
                    reason="Collect the initial page observation.",
                ),
                reason="Collect the initial page observation.",
                expected_outcome="The target page is observed.",
            ),
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
                        step_id="step_003",
                        tool_call=ToolCall(
                            call_id="call_003",
                            tool_id="browser_extract",
                            reason="Extract visible page information after opening.",
                        ),
                        reason="Extract visible page information after opening.",
                        expected_outcome="Visible page information is available.",
                    ),
                    PlannedStep(
                        step_id="step_004",
                        tool_call=ToolCall(
                            call_id="call_004",
                            tool_id="finish_task",
                            arguments={
                                "summary_instruction": "Open-only browser task completed.",
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
                        step_id="step_003",
                        tool_call=ToolCall(
                            call_id="call_003",
                            tool_id="browser_click",
                            arguments={
                                "target_hint": task.action.target_hint,
                                "expected_effect": task.action.expected_effect.model_dump(
                                    mode="json"
                                ),
                            },
                            reason="Click the requested target and verify the expected effect.",
                        ),
                        reason="Click the requested target and verify the expected effect.",
                        expected_outcome="The requested click effect is verified.",
                    ),
                    PlannedStep(
                        step_id="step_004",
                        tool_call=ToolCall(
                            call_id="call_004",
                            tool_id="browser_extract",
                            reason="Extract visible page information after clicking.",
                        ),
                        reason="Extract visible page information after clicking.",
                        expected_outcome="Visible post-click page information is available.",
                    ),
                    PlannedStep(
                        step_id="step_005",
                        tool_call=ToolCall(
                            call_id="call_005",
                            tool_id="finish_task",
                            arguments={
                                "summary_instruction": "Browser click task completed.",
                            },
                            reason="Finish the browser click task.",
                        ),
                        reason="Finish the browser click task.",
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


class ToolCallParser:
    def parse(self, text: str) -> ParsedToolCalls:
        raw_text = _truncate_raw_text(text)
        try:
            parsed, parse_error = self._parse_json(text)
            if parse_error is not None:
                return ParsedToolCalls(
                    status="failed",
                    error_type="TOOL_CALL_PARSE_ERROR",
                    error_message=parse_error,
                    raw_text=raw_text,
                )

            items = _tool_call_items(parsed)
            if items is None:
                return ParsedToolCalls(
                    status="failed",
                    error_type="INVALID_TOOL_CALL",
                    error_message=_tool_call_items_error(parsed),
                    raw_text=raw_text,
                )

            tool_calls: list[ToolCall] = []
            for index, item in enumerate(items, start=1):
                if not isinstance(item, dict):
                    return ParsedToolCalls(
                        status="failed",
                        error_type="INVALID_TOOL_CALL",
                        error_message="Each tool call must be a JSON object.",
                        raw_text=raw_text,
                    )
                if not item.get("tool_id"):
                    return ParsedToolCalls(
                        status="failed",
                        error_type="INVALID_TOOL_CALL",
                        error_message="Tool call is missing required field tool_id.",
                        raw_text=raw_text,
                    )
                payload = dict(item)
                payload.setdefault("call_id", f"call_{index:03d}")
                payload.setdefault("arguments", {})
                tool_calls.append(ToolCall.model_validate(payload))

            return ParsedToolCalls(
                status="success",
                tool_calls=tool_calls,
                raw_text=raw_text,
            )
        except Exception as exc:
            return ParsedToolCalls(
                status="failed",
                error_type="INVALID_TOOL_CALL",
                error_message=str(exc),
                raw_text=raw_text,
            )

    def _parse_json(self, text: str) -> tuple[Any | None, str | None]:
        candidates = [
            text,
            *_fenced_json_blocks(text),
        ]
        extracted = _extract_first_json_value(text)
        if extracted is not None:
            candidates.append(extracted)

        last_error: str | None = None
        for candidate in candidates:
            try:
                return json.loads(candidate), None
            except json.JSONDecodeError as exc:
                last_error = f"JSON parse failed: {exc.msg} at line {exc.lineno} column {exc.colno}."
                continue
        return None, last_error or "JSON parse failed: no JSON object or array found."


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
                if not browser_action_seen and tool_id != "browser_open":
                    issues.append(
                        PlanValidationIssue(
                            issue_type="INVALID_TOOL_ORDER",
                            message="The first browser action must be browser_open.",
                            step_id=step.step_id,
                            tool_id=tool_id,
                        )
                    )
                browser_action_seen = True

            if tool_id == "browser_open":
                opened = True
            elif tool_id in _SESSION_BROWSER_TOOL_IDS and not opened:
                issues.append(
                    PlanValidationIssue(
                        issue_type="INVALID_TOOL_ORDER",
                        message=f"{tool_id} cannot run before browser_open.",
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
    if tool_id == "browser_open" and not arguments.get("url"):
        issues.append(
            PlanValidationIssue(
                issue_type="MISSING_REQUIRED_ARGUMENT",
                message="browser_open requires arguments.url.",
                step_id=step.step_id,
                tool_id=tool_id,
            )
        )
    if tool_id == "browser_click" and not arguments.get("target_hint"):
        issues.append(
            PlanValidationIssue(
                issue_type="MISSING_REQUIRED_ARGUMENT",
                message="browser_click requires arguments.target_hint.",
                step_id=step.step_id,
                tool_id=tool_id,
            )
        )


_BROWSER_TOOL_IDS = {
    "browser_open",
    "browser_observe",
    "browser_click",
    "browser_type",
    "browser_select",
    "browser_scroll",
    "browser_wait",
    "browser_extract",
    "browser_screenshot",
}

_SESSION_BROWSER_TOOL_IDS = _BROWSER_TOOL_IDS - {
    "browser_open",
}


def _tool_call_items(parsed: Any) -> list[Any] | None:
    if isinstance(parsed, dict):
        tool_calls = parsed.get("tool_calls")
        if isinstance(tool_calls, list):
            return tool_calls
        if isinstance(tool_calls, dict):
            return [tool_calls]
        return None
    if isinstance(parsed, list):
        return parsed
    return None


def _tool_call_items_error(parsed: Any) -> str:
    if isinstance(parsed, dict):
        if "tool_calls" not in parsed:
            return "Parsed JSON object is missing tool_calls."
        return "Parsed JSON field tool_calls must be a list or object."
    return "Parsed JSON root must be a list or an object containing tool_calls."


def _fenced_json_blocks(text: str) -> list[str]:
    return re.findall(r"```(?:json)?\s*(.*?)```", text, flags=re.DOTALL | re.IGNORECASE)


def _extract_first_json_value(text: str) -> str | None:
    starts = [(idx, char) for idx, char in enumerate(text) if char in "{["]
    for start, opener in starts:
        closer = "}" if opener == "{" else "]"
        depth = 0
        in_string = False
        escape = False
        for index in range(start, len(text)):
            char = text[index]
            if in_string:
                if escape:
                    escape = False
                elif char == "\\":
                    escape = True
                elif char == '"':
                    in_string = False
                continue
            if char == '"':
                in_string = True
                continue
            if char == opener:
                depth += 1
            elif char == closer:
                depth -= 1
                if depth == 0:
                    return text[start : index + 1]
        continue
    return None


def _truncate_raw_text(text: str) -> str:
    if len(text) <= 8000:
        return text
    return f"{text[:8000]}..."
