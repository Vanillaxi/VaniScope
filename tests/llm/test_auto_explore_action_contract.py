from __future__ import annotations

import json
from pathlib import Path

import pytest

from webscoper.runtime.execution.handler import WebAgentExecutionHandler
from webscoper.runtime.llm.auto_explore import (
    AutoExploreActionPlanner,
    parse_auto_explore_decision,
)
from webscoper.runtime.llm.client import BaseLLMClient
from webscoper.schemas.llm import LLMRequest, LLMResponse
from webscoper.schemas.task import TaskSpec
from webscoper.workflows.langgraph_backend.nodes import LangGraphWorkflowNodes


def test_normalizer_accepts_plain_valid_json() -> None:
    decision, record = parse_auto_explore_decision(
        json.dumps(
            {
                "reasoning_summary": "Visible content is enough.",
                "action": {
                    "type": "extract",
                    "instruction": "Extract visible profile information.",
                    "expected_effect": {"type": "none"},
                    "risk_level": "read_only",
                },
            }
        )
    )

    assert decision is not None
    assert decision.action.type == "browser_extract"
    assert record["validation_status"] == "success"


def test_normalizer_accepts_markdown_fenced_json() -> None:
    decision, _record = parse_auto_explore_decision(
        """```json
{"reasoning_summary":"Enough info.","action":{"type":"extract"}}
```""",
        user_goal="Summarize the page.",
    )

    assert decision is not None
    assert decision.action.type == "browser_extract"
    assert decision.action.instruction


def test_normalizer_extracts_json_from_prose() -> None:
    decision, _record = parse_auto_explore_decision(
        'Here is the action: {"reason":"Need repos.","action":{"type":"click","target":"Repositories"}}',
    )

    assert decision is not None
    assert decision.reasoning_summary == "Need repos."
    assert decision.action.type == "browser_click"
    assert decision.action.target_hint == "Repositories"


def test_action_type_browser_extract_maps_to_extract() -> None:
    decision, _record = parse_auto_explore_decision(
        '{"action_type":"browser_extract","summary":"Collect visible information."}',
    )

    assert decision is not None
    assert decision.action.type == "browser_extract"
    assert decision.action.instruction == "Collect visible information."


def test_click_alias_maps_to_click_intent() -> None:
    decision, _record = parse_auto_explore_decision(
        '{"tool":"click","target_text":"Repositories"}',
    )

    assert decision is not None
    assert decision.action.type == "browser_click"
    assert decision.action.target_hint == "Repositories"


def test_action_string_extract_is_wrapped() -> None:
    decision, _record = parse_auto_explore_decision(
        '{"action":"extract"}',
        user_goal="Summarize the visible profile.",
    )

    assert decision is not None
    assert decision.reasoning_summary == "No reasoning summary provided."
    assert decision.action.type == "browser_extract"
    assert decision.action.instruction


def test_missing_risk_and_expected_effect_get_defaults() -> None:
    decision, _record = parse_auto_explore_decision(
        '{"action":{"type":"extract","instruction":"Extract visible text."}}',
    )

    assert decision is not None
    assert decision.action.risk_level == "read_only"
    assert decision.action.expected_effect.type == "none"


def test_click_intent_missing_target_hint_fails_validation() -> None:
    decision, record = parse_auto_explore_decision(
        '{"action":{"type":"click_intent"}}',
    )

    assert decision is None
    assert record["validation_status"] == "failed"
    assert "browser_click requires target_hint" in json.dumps(record["validation_errors"])


def test_extract_missing_instruction_uses_user_goal() -> None:
    decision, _record = parse_auto_explore_decision(
        '{"action":{"type":"extract"}}',
        user_goal="Understand this GitHub profile.",
    )

    assert decision is not None
    assert "Understand this GitHub profile" in (decision.action.instruction or "")


@pytest.mark.parametrize(
    "payload",
    [
        '{"action":{"type":"click_intent","target_hint":"Repo","selector":"#repo"}}',
        '{"action":{"type":"click_intent","target_hint":"Repo","playwright":"page.click()"}}',
        '{"action":{"type":"click_intent","target_hint":"Repo","javascript":"document.cookie"}}',
        '{"action":{"type":"click_intent","target_hint":"Repo","xpath":"//a"}}',
    ],
)
def test_forbidden_raw_automation_fields_are_rejected(payload: str) -> None:
    decision, record = parse_auto_explore_decision(payload)

    assert decision is None
    assert "Forbidden raw automation fields" in json.dumps(record["validation_errors"])


def test_qwen_style_output_fixture_can_be_normalized() -> None:
    content = """
好的，下一步建议如下：
```json
{
  "reason": "The GitHub profile is visible and enough for first extraction.",
  "tool_name": "browser_extract",
  "summary": "Extract profile bio, followers, pinned repositories, and technical signals.",
  "risk_level": "safe"
}
```
"""

    decision, record = parse_auto_explore_decision(content)

    assert decision is not None
    assert decision.action.type == "browser_extract"
    assert decision.action.risk_level == "read_only"
    assert record["validation_status"] == "success"


@pytest.mark.asyncio
async def test_invalid_first_output_triggers_repair_once_and_succeeds(tmp_path: Path) -> None:
    class RepairingClient(BaseLLMClient):
        def __init__(self) -> None:
            self.calls = 0

        async def generate(self, request: LLMRequest) -> LLMResponse:
            self.calls += 1
            if self.calls == 1:
                return LLMResponse(content='{"action":{"type":"click_intent"}}', model="test")
            return LLMResponse(content='{"action":"finish"}', model="test")

    context = _context(tmp_path)
    client = RepairingClient()
    planner = AutoExploreActionPlanner(client, repair_attempts=1)

    decision = await planner.decide(
        context=context.snapshot(),
        observation=None,
        history=[],
        step_index=1,
    )

    assert decision.action.type == "finish_task"
    assert client.calls == 2
    assert len(planner.repair_requests) == 1
    assert planner.validation_records[-1]["validation_status"] == "success"


@pytest.mark.asyncio
async def test_repair_failure_records_validation_artifact(tmp_path: Path) -> None:
    class InvalidClient(BaseLLMClient):
        async def generate(self, request: LLMRequest) -> LLMResponse:
            return LLMResponse(content='{"action":{"type":"click_intent"}}', model="test")

    context = _context(tmp_path)
    planner = AutoExploreActionPlanner(InvalidClient(), repair_attempts=1)

    with pytest.raises(RuntimeError, match="LLM_ACTION_SCHEMA_INVALID"):
        await planner.decide(
            context=context.snapshot(),
            observation=None,
            history=[],
            step_index=1,
        )

    nodes = object.__new__(LangGraphWorkflowNodes)
    artifact_path = LangGraphWorkflowNodes._write_action_validation_artifact(
        nodes,
        context,
        planner,
    )
    payload = json.loads(Path(artifact_path).read_text(encoding="utf-8"))

    assert payload["status"] == "failed"
    assert payload["repair_attempted"] is True
    assert payload["repair_success"] is False
    assert payload["validation_records"]
    assert payload["final_action"] is None


def _context(tmp_path: Path):
    task = TaskSpec(
        task_id="auto_contract_task",
        raw_input="Summarize the page.",
        target_url=Path("tests/fixtures/mock_site/basic.html").resolve().as_uri(),
        mode="auto_explore",
        goal="Summarize the page.",
    )
    return WebAgentExecutionHandler(output_root=tmp_path).build_context(task)
