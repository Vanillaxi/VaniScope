from __future__ import annotations

from pathlib import Path

import pytest

from webscoper.runtime.tool_executor import LocalToolExecutor
from webscoper.runtime.trace import TraceRecorder
from webscoper.schemas.context import RuntimeState, TraceContext, WebAgentContextSnapshot
from webscoper.schemas.task import TaskSpec
from webscoper.schemas.tool_call import ToolCall
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
