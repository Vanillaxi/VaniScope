from __future__ import annotations

from webscoper.schemas.tool_call import ToolCall, ToolExecutionRecord, ToolResult


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
