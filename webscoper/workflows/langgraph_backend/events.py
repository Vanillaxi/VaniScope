from __future__ import annotations

from typing import Any

from webscoper.runtime.context import WebAgentContext
from webscoper.workflows.langgraph_backend.state_io import json_safe
from webscoper.workflows.state import VaniScopeGraphState


class WorkflowEventEmitter:
    def __init__(self, handler: Any) -> None:
        self.handler = handler

    def emit_workflow_event(self, kind: str, payload: dict[str, Any]) -> None:
        message = kind.replace("_", " ").title()
        self._emit(kind, message, payload)

    def emit_node_started(self, state: VaniScopeGraphState, node: str) -> None:
        payload = {"backend": "langgraph", "node": node}
        self.record_state_event(state, "workflow_node_started", payload)
        self.emit_workflow_event("workflow_node_started", payload)

    def emit_node_finished(
        self,
        state: VaniScopeGraphState,
        node: str,
        *,
        status: str | None,
        error: str | None = None,
    ) -> None:
        payload: dict[str, Any] = {
            "backend": "langgraph",
            "node": node,
            "status": status,
        }
        if error is not None:
            payload["error"] = error
        self.record_state_event(state, "workflow_node_finished", payload)
        self.emit_workflow_event("workflow_node_finished", payload)

    def emit_tool_event(
        self,
        context: WebAgentContext,
        kind: str,
        message: str,
        payload: dict[str, Any] | None = None,
    ) -> None:
        event_payload = {"run_id": context.run_id}
        event_payload.update(payload or {})
        self._emit(kind, message, event_payload)

    def record_state_event(
        self,
        state: VaniScopeGraphState,
        event: str,
        payload: dict[str, Any],
    ) -> None:
        state.setdefault("events", []).append(
            {"event": event, "payload": json_safe(payload)}
        )

    def _emit(self, kind: str, message: str, payload: dict[str, Any]) -> None:
        try:
            self.handler._emit_event(kind, message, json_safe(payload))
        except Exception:
            return
