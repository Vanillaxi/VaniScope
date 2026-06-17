from __future__ import annotations

import json

from webscoper.runtime.tool_call_parser import ToolCallParser


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
