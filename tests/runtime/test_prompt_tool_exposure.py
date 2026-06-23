from __future__ import annotations

import json
from pathlib import Path

import pytest

from webscoper.runtime.execution.handler import WebAgentExecutionHandler
from webscoper.runtime.llm.auto_explore import AutoExploreActionPlanner
from webscoper.runtime.llm.client import BaseLLMClient
from webscoper.runtime.prompt.builder import DynamicPromptBuilder, select_prompt_tools
from webscoper.schemas.browser import PageObservation
from webscoper.schemas.llm import LLMRequest, LLMResponse
from webscoper.schemas.runtime import BudgetContext
from webscoper.schemas.task import TaskSpec
from webscoper.tools.registry import create_default_tool_registry


def test_initial_auto_explore_prompt_does_not_include_all_registered_browser_tools(
    tmp_path: Path,
) -> None:
    context = _context(
        tmp_path,
        TaskSpec(
            task_id="initial_public",
            raw_input="Summarize this GitHub profile.",
            target_url="https://github.com/octocat",
            mode="auto_explore",
            goal="Summarize this GitHub profile.",
        ),
    )
    result = DynamicPromptBuilder(create_default_tool_registry()).build(context.snapshot())

    assert result.core_tool_ids == ["browser_open", "ask_human", "finish_task", "tool_search"]
    assert "browser_upload_file" not in result.prompt_text
    assert result.prompt_preview_text is not None
    assert "browser_upload_file: disabled/reserved" in result.prompt_preview_text


def test_observed_public_web_hides_disabled_and_input_tools(
    tmp_path: Path,
) -> None:
    context = _context(
        tmp_path,
        TaskSpec(
            task_id="observed_public",
            raw_input="Summarize this public page.",
            target_url="https://example.com",
            mode="auto_explore",
        ),
    )
    selection = select_prompt_tools(
        create_default_tool_registry(),
        context=context.snapshot(),
        observation=_observation("https://example.com"),
    )

    assert selection.available_actions == [
        "browser_observe",
        "browser_click",
        "browser_scroll",
        "browser_wait",
        "browser_extract",
        "browser_screenshot",
        "ask_human",
        "finish_task",
        "tool_search",
    ]
    assert selection.hidden_tools["browser_type"] == "hidden on public web by default"
    assert selection.hidden_tools["browser_select"] == "hidden on public web by default"
    assert selection.disabled_tools["browser_upload_file"] == "disabled/reserved"
    assert selection.disabled_tools["browser_download"] == "disabled/reserved"
    assert selection.disabled_tools["browser_drag"] == "disabled/reserved"


def test_local_fixture_form_task_can_expose_type_and_select(tmp_path: Path) -> None:
    fixture_url = Path("tests/fixtures/mock_site/browser_tools_v2.html").resolve().as_uri()
    context = _context(
        tmp_path,
        TaskSpec(
            task_id="local_form",
            raw_input="Fill the form and select an option.",
            target_url=fixture_url,
            mode="auto_explore",
            tags=["form"],
        ),
    )
    selection = select_prompt_tools(
        create_default_tool_registry(),
        context=context.snapshot(),
        observation=_observation(fixture_url),
    )

    assert "browser_type" in selection.available_actions
    assert "browser_select" in selection.available_actions
    assert "browser_type" not in selection.hidden_tools
    assert "browser_select" not in selection.hidden_tools


def test_lazy_tools_and_skill_catalog_are_compact_until_loaded(tmp_path: Path) -> None:
    context = _context(
        tmp_path,
        TaskSpec(
            task_id="lazy_public",
            raw_input="Summarize this page.",
            target_url="https://example.com",
            mode="auto_explore",
        ),
    )
    result = DynamicPromptBuilder(create_default_tool_registry()).build(context.snapshot())

    assert result.lazy_tool_ids == [
        "github_fetch_issue",
        "github_fetch_pr",
        "docs_extract",
        "table_extract",
    ]
    for tool_id in result.lazy_tool_ids:
        assert tool_id not in result.core_tool_ids
    assert "Use the opened documentation page as the primary source." not in result.prompt_text
    assert "Treat the opened issue or PR page as the source of truth." not in result.prompt_text
    assert "# Skill Catalog" in result.prompt_text
    assert "github_issue_research" in result.prompt_text


def test_prompt_built_event_reports_selected_tools_not_full_registry(
    tmp_path: Path,
) -> None:
    events: list[dict] = []
    task = TaskSpec(
        task_id="event_public",
        raw_input="Summarize this page.",
        target_url="https://example.com",
        mode="auto_explore",
    )
    handler = WebAgentExecutionHandler(
        output_root=tmp_path,
        event_sink=lambda kind, message, payload: events.append(
            {"kind": kind, "message": message, "payload": payload}
        ),
    )
    context = handler.build_context(task)

    result = handler.build_prompt(context)
    event = [row for row in events if row["kind"] == "prompt_built"][0]

    assert event["payload"]["core_tool_ids"] == result.core_tool_ids
    assert event["payload"]["core_tool_ids"] == [
        "browser_open",
        "ask_human",
        "finish_task",
        "tool_search",
    ]
    assert "browser_upload_file" not in event["payload"]["core_tool_ids"]
    prompt_context = json.loads(
        (context.run_dir / "prompt_context.json").read_text(encoding="utf-8")
    )
    assert prompt_context["available_actions"] == result.core_tool_ids
    assert prompt_context["lazy_tool_ids"] == result.lazy_tool_ids


@pytest.mark.asyncio
async def test_real_llm_auto_explore_request_uses_selected_observed_tools(
    tmp_path: Path,
) -> None:
    client = RecordingClient(
        '{"action":{"type":"browser_extract","instruction":"Extract visible profile details."}}'
    )
    context = _context(
        tmp_path,
        TaskSpec(
            task_id="real_prompt_public",
            raw_input="Summarize this GitHub profile.",
            target_url="https://github.com/octocat",
            mode="auto_explore",
            goal="Summarize this GitHub profile.",
            budget=BudgetContext(max_prompt_tokens=12000),
        ),
    )
    planner = AutoExploreActionPlanner(client)

    await planner.decide(
        context=context.snapshot(),
        observation=_observation("https://github.com/octocat"),
        history=[],
        step_index=2,
    )

    request = client.requests[0]
    assert request.metadata["available_actions"] == [
        "browser_observe",
        "browser_click",
        "browser_scroll",
        "browser_wait",
        "browser_extract",
        "browser_screenshot",
        "ask_human",
        "finish_task",
        "tool_search",
    ]
    prompt_text = "\n".join(message.content for message in request.messages)
    assert "browser_upload_file" not in prompt_text
    assert "browser_download" not in prompt_text
    assert "browser_drag" not in prompt_text
    assert "browser_type" not in request.metadata["available_actions"]
    assert "browser_select" not in request.metadata["available_actions"]
    assert len(prompt_text) < context.task.budget.max_prompt_tokens * 4


class RecordingClient(BaseLLMClient):
    def __init__(self, response: str) -> None:
        self.response = response
        self.requests: list[LLMRequest] = []

    async def generate(self, request: LLMRequest) -> LLMResponse:
        self.requests.append(request)
        return LLMResponse(content=self.response, model="test")


def _context(tmp_path: Path, task: TaskSpec):
    return WebAgentExecutionHandler(output_root=tmp_path).build_context(task)


def _observation(url: str) -> PageObservation:
    return PageObservation(
        url=url,
        title="Example",
        visible_text_summary="Example visible text.",
        interactive_elements=[],
        risk_signals=[],
    )
