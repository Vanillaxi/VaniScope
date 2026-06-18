from __future__ import annotations

import json
from typing import Any

from webscoper.runtime.context import WebAgentContext
from webscoper.schemas.task import TaskSpec
from webscoper.workflows.state import VaniScopeGraphState


TERMINAL_GRAPH_STATUSES = {"failed", "blocked", "requires_approval"}


def coerce_task(request: Any) -> TaskSpec:
    if isinstance(request, TaskSpec):
        return request
    if isinstance(request, dict):
        return TaskSpec.model_validate(request)
    raise TypeError(f"Unsupported workflow request type: {type(request).__name__}")


def graph_interrupt_type():
    try:
        from langgraph.errors import GraphInterrupt
    except ImportError:
        return ()
    return GraphInterrupt


def read_json_file(path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def read_json_safe_from_transcript_tail(
    context: WebAgentContext,
    event_type: str,
) -> dict[str, Any] | None:
    if not context.transcript_store.transcript_path.exists():
        return None
    for line in reversed(
        context.transcript_store.transcript_path.read_text(encoding="utf-8").splitlines()
    ):
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("event_type") == event_type:
            payload = event.get("payload")
            return payload if isinstance(payload, dict) else None
    return None


def state_thread_id(context: WebAgentContext, thread_id: str | None) -> str:
    return thread_id or context.run_id


def to_json_safe_state(state: VaniScopeGraphState | dict[str, Any]) -> dict[str, Any]:
    return json.loads(json.dumps(state, ensure_ascii=False, default=str))


def json_safe(value: Any) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=False, default=str))
