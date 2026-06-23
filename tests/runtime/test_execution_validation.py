from __future__ import annotations

# From test_execution_handler_plan_validation.py
import json
from pathlib import Path

import pytest

from webscoper.runtime.execution.handler import WebAgentExecutionHandler
from webscoper.runtime.llm.client import BaseLLMClient
from webscoper.schemas.llm import LLMRequest, LLMResponse
from webscoper.schemas.task import TaskSpec


class LazyToolLLMClient(BaseLLMClient):
    async def generate(self, request: LLMRequest) -> LLMResponse:
        return LLMResponse(
            content=json.dumps(
                {
                    "tool_calls": [
                        {
                            "call_id": "call_001",
                            "tool_id": "web_search",
                            "arguments": {"query": "playwright"},
                        }
                    ]
                }
            ),
            model="mock-real-llm",
        )


@pytest.mark.asyncio
async def test_execution_handler_blocks_invalid_plan_before_loop(
    tmp_path: Path,
) -> None:
    task = TaskSpec(
        task_id="handler_invalid_plan",
        raw_input="Search the web.",
        target_url=Path("tests/fixtures/mock_site/basic.html").resolve().as_uri(),
    )
    handler = WebAgentExecutionHandler(
        output_root=tmp_path,
        planner_mode="real_llm",
        llm_client=LazyToolLLMClient(),
    )

    with pytest.raises(RuntimeError, match="LAZY_TOOL_NOT_EXECUTABLE"):
        await handler.run(task)

    context = handler.last_context
    assert context is not None
    event_types = _jsonl_values(context.transcript_store.transcript_path, "event_type")
    assert "llm_response" in event_types
    assert "plan_built" in event_types
    assert "plan_validation_completed" in event_types
    assert "plan_validation_failed" in event_types
    assert "execution_failed" in event_types
    assert "tool_call_completed" not in event_types


def _jsonl_values(path: Path, key: str) -> list[str]:
    return [
        json.loads(line)[key]
        for line in path.read_text(encoding="utf-8").splitlines()
    ]

# From test_plan_validator.py
from pathlib import Path

from webscoper.runtime.execution.context import WebAgentContext
from webscoper.runtime.execution.plan_validator import PlanValidator
from webscoper.runtime.execution.planner import DeterministicTaskPlanner
from webscoper.runtime.artifacts.trace import TraceRecorder
from webscoper.runtime.artifacts.transcript import TranscriptStore
from webscoper.schemas.browser import ActionContract, ExpectedEffect
from webscoper.schemas.runtime import RuntimeState
from webscoper.schemas.tool import ExecutionPlan, PlannedStep
from webscoper.schemas.task import BudgetContext, TaskSpec
from webscoper.schemas.tool import ToolCall
from webscoper.schemas.runtime import VersionContext
from webscoper.tools.registry import create_default_tool_registry


def test_deterministic_open_only_plan_validates_success(tmp_path: Path) -> None:
    task = _task(action=False)
    plan = DeterministicTaskPlanner().build_plan(task)

    result = _validator().validate(plan, _context(tmp_path, task).snapshot())

    assert result.ok
    assert result.issues == []


def test_plan_validator_reports_core_invalid_plan_cases(tmp_path: Path) -> None:
    cases = [
        (
            _task(),
            _plan(ToolCall(call_id="call_001", tool_id="browser_magic_click")),
            "UNKNOWN_TOOL",
        ),
        (
            _task(),
            _plan(
                ToolCall(
                    call_id="call_001",
                    tool_id="web_search",
                    arguments={"query": "x"},
                )
            ),
            "LAZY_TOOL_NOT_EXECUTABLE",
        ),
        (
            _task(),
            _plan(ToolCall(call_id="call_001", tool_id="browser_open")),
            "MISSING_REQUIRED_ARGUMENT",
        ),
        (
            _task(action=True),
            _plan(
                ToolCall(
                    call_id="call_001",
                    tool_id="browser_click",
                    arguments={
                        "target_hint": _task(action=True).action.target_hint,
                        "expected_effect": _task(
                            action=True
                        ).action.expected_effect.model_dump(mode="json"),
                    },
                )
            ),
            "INVALID_TOOL_ORDER",
        ),
        (
            _task(),
            _plan(
                ToolCall(
                    call_id="call_001",
                    tool_id="browser_open",
                    arguments={"url": _task().target_url},
                ),
                ToolCall(call_id="call_002", tool_id="finish_task"),
                ToolCall(call_id="call_003", tool_id="browser_extract"),
            ),
            "INVALID_TOOL_ORDER",
        ),
        (
            _task(budget=BudgetContext(max_steps=1)),
            DeterministicTaskPlanner().build_plan(
                _task(budget=BudgetContext(max_steps=1))
            ),
            "MAX_STEPS_EXCEEDED",
        ),
    ]

    for task, plan, expected_issue in cases:
        result = _validator().validate(plan, _context(tmp_path, task).snapshot())
        assert expected_issue in _issue_types(result)


def _validator() -> PlanValidator:
    return PlanValidator(create_default_tool_registry())


def _plan(*calls: ToolCall) -> ExecutionPlan:
    return ExecutionPlan(
        plan_id="test_plan",
        task_id="test_task",
        steps=[
            PlannedStep(
                step_id=f"step_{index:03d}",
                tool_call=call,
                reason="test",
            )
            for index, call in enumerate(calls, start=1)
        ],
    )


def _task(
    action: bool = False,
    budget: BudgetContext | None = None,
) -> TaskSpec:
    action_contract = None
    if action:
        action_contract = ActionContract(
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
    return TaskSpec(
        task_id="test_task",
        raw_input="Open local basic mock.",
        target_url=Path("tests/fixtures/mock_site/basic.html").resolve().as_uri(),
        action=action_contract,
        budget=budget or BudgetContext(),
    )


def _context(tmp_path: Path, task: TaskSpec) -> WebAgentContext:
    return WebAgentContext(
        task=task,
        run_id="validator_test",
        run_dir=tmp_path,
        trace_recorder=TraceRecorder(run_dir=tmp_path, run_id="validator_test"),
        transcript_store=TranscriptStore(run_dir=tmp_path, run_id="validator_test"),
        version=VersionContext(),
        state=RuntimeState(status="running"),
    )


def _issue_types(result) -> list[str]:
    return [issue.issue_type for issue in result.issues]
