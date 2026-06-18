from __future__ import annotations

# From test_execution_handler_plan_validation.py
import json
from pathlib import Path

import pytest

from webscoper.runtime.execution import WebAgentExecutionHandler
from webscoper.runtime.llm_client import BaseLLMClient
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

from webscoper.runtime.context import WebAgentContext
from webscoper.runtime.plan_validator import PlanValidator
from webscoper.runtime.planner import DeterministicTaskPlanner
from webscoper.runtime.trace import TraceRecorder
from webscoper.runtime.transcript import TranscriptStore
from webscoper.schemas.action import ActionContract, ExpectedEffect
from webscoper.schemas.context import RuntimeState
from webscoper.schemas.plan import ExecutionPlan, PlannedStep
from webscoper.schemas.task import BudgetContext, TaskSpec
from webscoper.schemas.tool_call import ToolCall
from webscoper.schemas.version import VersionContext
from webscoper.tools.registry import create_default_tool_registry


def test_deterministic_open_only_plan_validates_success(tmp_path: Path) -> None:
    task = _task(action=False)
    plan = DeterministicTaskPlanner().build_plan(task)

    result = _validator().validate(plan, _context(tmp_path, task).snapshot())

    assert result.ok
    assert result.issues == []


def test_unknown_tool_returns_unknown_tool(tmp_path: Path) -> None:
    task = _task()
    plan = _plan(
        ToolCall(call_id="call_001", tool_id="browser_magic_click"),
    )

    result = _validator().validate(plan, _context(tmp_path, task).snapshot())

    assert _issue_types(result) == ["UNKNOWN_TOOL"]


def test_lazy_tool_returns_lazy_tool_not_executable(tmp_path: Path) -> None:
    task = _task()
    plan = _plan(
        ToolCall(call_id="call_001", tool_id="web_search", arguments={"query": "x"}),
    )

    result = _validator().validate(plan, _context(tmp_path, task).snapshot())

    assert "LAZY_TOOL_NOT_EXECUTABLE" in _issue_types(result)


def test_missing_url_returns_missing_required_argument(tmp_path: Path) -> None:
    task = _task()
    plan = _plan(
        ToolCall(call_id="call_001", tool_id="browser_open_observe"),
    )

    result = _validator().validate(plan, _context(tmp_path, task).snapshot())

    assert "MISSING_REQUIRED_ARGUMENT" in _issue_types(result)


def test_click_before_open_returns_invalid_tool_order(tmp_path: Path) -> None:
    task = _task(action=True)
    plan = _plan(
        ToolCall(
            call_id="call_001",
            tool_id="browser_click_intent",
            arguments={"action": task.action.model_dump(mode="json")},
        )
    )

    result = _validator().validate(plan, _context(tmp_path, task).snapshot())

    assert "INVALID_TOOL_ORDER" in _issue_types(result)


def test_finish_task_not_last_returns_invalid_tool_order(tmp_path: Path) -> None:
    task = _task()
    plan = _plan(
        ToolCall(call_id="call_001", tool_id="browser_open_observe", arguments={"url": task.target_url}),
        ToolCall(call_id="call_002", tool_id="finish_task"),
        ToolCall(call_id="call_003", tool_id="browser_extract"),
    )

    result = _validator().validate(plan, _context(tmp_path, task).snapshot())

    assert "INVALID_TOOL_ORDER" in _issue_types(result)


def test_max_steps_exceeded_returns_max_steps_exceeded(tmp_path: Path) -> None:
    task = _task(budget=BudgetContext(max_steps=1))
    plan = DeterministicTaskPlanner().build_plan(task)

    result = _validator().validate(plan, _context(tmp_path, task).snapshot())

    assert "MAX_STEPS_EXCEEDED" in _issue_types(result)


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
