from __future__ import annotations

import json
import re
from typing import Any

from webscoper.schemas.llm import ParsedToolCalls
from webscoper.schemas.tool_call import ToolCall


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
