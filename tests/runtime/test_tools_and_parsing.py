from __future__ import annotations

# From test_local_tool_executor.py
from pathlib import Path

import pytest

from webscoper.runtime.execution.tool_executor import LocalToolExecutor
from webscoper.runtime.artifacts.trace import TraceRecorder
from webscoper.schemas.runtime import RuntimeState, TraceContext, WebAgentContextSnapshot
from webscoper.schemas.task import TaskSpec
from webscoper.schemas.tool import ToolCall
from webscoper.browser.tool_runtime import StatefulBrowserToolRuntime
from webscoper.tools.registry import create_default_tool_registry


@pytest.mark.asyncio
async def test_local_tool_executor_rejects_unknown_and_lazy_tools(
    tmp_path: Path,
) -> None:
    executor = _executor(tmp_path)
    context = _context(tmp_path)
    cases = [
        (ToolCall(call_id="call_001", tool_id="unknown_tool"), "UNKNOWN_TOOL"),
        (
            ToolCall(
                call_id="call_002",
                tool_id="web_search",
                arguments={"query": "test"},
            ),
            "LAZY_TOOL_NOT_LOADED",
        ),
    ]

    for call, error_type in cases:
        result = await executor.execute(call, context)
        assert result.status == "failed"
        assert result.error_type == error_type


def _executor(tmp_path: Path) -> LocalToolExecutor:
    recorder = TraceRecorder(run_dir=tmp_path / "run", run_id="run_tool_executor")
    browser_runtime = StatefulBrowserToolRuntime(trace_recorder=recorder)
    return LocalToolExecutor(
        tool_registry=create_default_tool_registry(),
        browser_runtime=browser_runtime,
    )


def _context(tmp_path: Path) -> WebAgentContextSnapshot:
    task = TaskSpec(
        task_id="executor_task",
        raw_input="Executor test.",
        target_url="file:///tmp/basic.html",
    )
    return WebAgentContextSnapshot(
        task=task,
        trace=TraceContext(
            run_id="run_tool_executor",
            run_dir=str(tmp_path / "run"),
            trace_path=str(tmp_path / "run" / "trace.jsonl"),
            transcript_path=str(tmp_path / "run" / "transcript.jsonl"),
        ),
        budget=task.budget,
        safety=task.safety,
        state=RuntimeState(status="running"),
    )

# From test_tool_call_parser.py
import json

from webscoper.runtime.execution.tool_call_parser import ToolCallParser


def test_tool_call_parser_accepts_supported_shapes() -> None:
    cases = [
        (
            json.dumps(
                {
                    "tool_calls": [
                        {
                            "call_id": "call_001",
                            "tool_id": "browser_open_observe",
                            "arguments": {"url": "file:///tmp/basic.html"},
                            "reason": "Open the target page.",
                        }
                    ]
                }
            ),
            "browser_open_observe",
        ),
        (
            """```json
{
  "tool_calls": [
    {
      "call_id": "call_001",
      "tool_id": "browser_extract",
      "arguments": {}
    }
  ]
}
```""",
            "browser_extract",
        ),
        (
            json.dumps(
                [
                    {
                        "call_id": "call_001",
                        "tool_id": "finish_task",
                        "arguments": {"summary": "Done."},
                    }
                ]
            ),
            "finish_task",
        ),
        (
            json.dumps(
                {
                    "tool_calls": {
                        "call_id": "call_001",
                        "tool_id": "browser_open_observe",
                        "arguments": {"url": "file:///tmp/basic.html"},
                    }
                }
            ),
            "browser_open_observe",
        ),
    ]

    for payload, tool_id in cases:
        result = ToolCallParser().parse(payload)
        assert result.status == "success"
        assert result.tool_calls[0].tool_id == tool_id


def test_tool_call_parser_autofills_call_id_and_rejects_bad_input() -> None:
    autofilled = ToolCallParser().parse(
        json.dumps({"tool_calls": [{"tool_id": "browser_extract"}]})
    )
    invalid_tool_call = ToolCallParser().parse(
        json.dumps({"tool_calls": [{"call_id": "call_001", "arguments": {}}]})
    )
    non_json = ToolCallParser().parse("I think you should click the button.")

    assert autofilled.status == "success"
    assert autofilled.tool_calls[0].call_id == "call_001"
    assert autofilled.tool_calls[0].arguments == {}
    assert invalid_tool_call.status == "failed"
    assert invalid_tool_call.error_type == "INVALID_TOOL_CALL"
    assert non_json.status == "failed"
    assert non_json.error_type == "TOOL_CALL_PARSE_ERROR"

# From test_tool_registry.py
from webscoper.tools.registry import create_default_tool_registry


def test_default_tool_registry_snapshot_and_search() -> None:
    registry = create_default_tool_registry()

    snapshot = registry.snapshot()
    core_tool_ids = {tool.tool_id for tool in snapshot.core_tools}
    lazy_tool_ids = {tool.tool_id for tool in snapshot.lazy_tools}
    search_result = registry.search("github issue")
    search_tool_ids = {tool.tool_id for tool in search_result.matches}

    assert "browser_open_observe" in core_tool_ids
    assert "browser_click_intent" in core_tool_ids
    assert "github_fetch_issue" in lazy_tool_ids
    assert "github_fetch_issue" in search_tool_ids
