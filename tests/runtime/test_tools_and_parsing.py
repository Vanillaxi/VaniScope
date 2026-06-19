from __future__ import annotations

# From test_local_tool_executor.py
from pathlib import Path

import pytest

from webscoper.runtime.execution.tool_executor import LocalToolExecutor
from webscoper.runtime.artifacts.trace import TraceRecorder
from webscoper.schemas.runtime import RuntimeState, TraceContext, WebAgentContextSnapshot
from webscoper.schemas.task import TaskSpec
from webscoper.schemas.tool import ToolCall
from webscoper.tools.browser_tools import StatefulBrowserToolRuntime
from webscoper.tools.registry import create_default_tool_registry


@pytest.mark.asyncio
async def test_local_tool_executor_returns_unknown_tool(tmp_path: Path) -> None:
    executor = _executor(tmp_path)
    context = _context(tmp_path)

    result = await executor.execute(
        ToolCall(call_id="call_001", tool_id="unknown_tool"),
        context,
    )

    assert result.status == "failed"
    assert result.error_type == "UNKNOWN_TOOL"


@pytest.mark.asyncio
async def test_local_tool_executor_does_not_execute_lazy_tool(tmp_path: Path) -> None:
    executor = _executor(tmp_path)
    context = _context(tmp_path)

    result = await executor.execute(
        ToolCall(call_id="call_001", tool_id="web_search", arguments={"query": "test"}),
        context,
    )

    assert result.status == "failed"
    assert result.error_type == "LAZY_TOOL_NOT_LOADED"


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


def test_parse_plain_json_dict() -> None:
    result = ToolCallParser().parse(
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
        )
    )

    assert result.status == "success"
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0].tool_id == "browser_open_observe"


def test_parse_fenced_json() -> None:
    result = ToolCallParser().parse(
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
```"""
    )

    assert result.status == "success"
    assert result.tool_calls[0].tool_id == "browser_extract"


def test_parse_json_array() -> None:
    result = ToolCallParser().parse(
        json.dumps(
            [
                {
                    "call_id": "call_001",
                    "tool_id": "finish_task",
                    "arguments": {"summary": "Done."},
                }
            ]
        )
    )

    assert result.status == "success"
    assert result.tool_calls[0].tool_id == "finish_task"


def test_parse_tool_calls_single_object() -> None:
    result = ToolCallParser().parse(
        json.dumps(
            {
                "tool_calls": {
                    "call_id": "call_001",
                    "tool_id": "browser_open_observe",
                    "arguments": {"url": "file:///tmp/basic.html"},
                }
            }
        )
    )

    assert result.status == "success"
    assert len(result.tool_calls) == 1
    assert result.tool_calls[0].tool_id == "browser_open_observe"


def test_parse_missing_call_id_autofills() -> None:
    result = ToolCallParser().parse(
        json.dumps(
            {
                "tool_calls": [
                    {
                        "tool_id": "browser_extract",
                    }
                ]
            }
        )
    )

    assert result.status == "success"
    assert result.tool_calls[0].call_id == "call_001"
    assert result.tool_calls[0].arguments == {}


def test_parse_missing_tool_id_fails() -> None:
    result = ToolCallParser().parse(
        json.dumps(
            {
                "tool_calls": [
                    {
                        "call_id": "call_001",
                        "arguments": {},
                    }
                ]
            }
        )
    )

    assert result.status == "failed"
    assert result.error_type == "INVALID_TOOL_CALL"


def test_parse_non_json_fails() -> None:
    result = ToolCallParser().parse("I think you should click the button.")

    assert result.status == "failed"
    assert result.error_type == "TOOL_CALL_PARSE_ERROR"

# From test_tool_call_schema.py
from webscoper.schemas.tool import ToolCall, ToolExecutionRecord, ToolResult


def test_tool_call_models_dump_json() -> None:
    call = ToolCall(
        call_id="call_001",
        tool_id="browser_open_observe",
        arguments={"url": "file:///tmp/basic.html"},
        reason="Open the page.",
    )
    result = ToolResult(
        call_id=call.call_id,
        tool_id=call.tool_id,
        status="success",
        output={"ok": True},
    )
    record = ToolExecutionRecord(call=call, result=result)

    payload = record.model_dump(mode="json")

    assert payload["call"]["call_id"] == "call_001"
    assert payload["call"]["tool_id"] == "browser_open_observe"
    assert payload["result"]["tool_id"] == "browser_open_observe"
    assert payload["result"]["status"] == "success"

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
