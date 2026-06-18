from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from webscoper.runtime.context import WebAgentContext
from webscoper.workflows.langgraph_approval import LangGraphApprovalBridge
from webscoper.workflows.langgraph_backend.state_io import to_json_safe_state
from webscoper.workflows.state import VaniScopeGraphState


class WorkflowArtifactWriter:
    def __init__(self, handler: Any) -> None:
        self.handler = handler

    def list_artifacts(
        self,
        output_dir: Path,
        include_pending: str | None = None,
    ) -> list[str]:
        if not output_dir.exists():
            return []
        artifacts = {path.name for path in output_dir.iterdir() if path.is_file()}
        if include_pending is not None:
            artifacts.add(include_pending)
        return sorted(artifacts)

    def write_workflow_state(
        self,
        state: VaniScopeGraphState | dict[str, Any],
        output_dir: Path,
    ) -> None:
        path = output_dir / "workflow_state.json"
        path.write_text(
            json.dumps(to_json_safe_state(state), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def write_approval_artifacts(
        self,
        context: WebAgentContext,
        approval_bridge: LangGraphApprovalBridge,
    ) -> None:
        self.handler.approval_store.write_jsonl_for_task(
            context.run_id,
            context.run_dir / "approvals.jsonl",
        )
        self.handler.approval_store.write_risk_report(
            context.run_id,
            context.run_dir / "risk_report.json",
        )
        self.handler.pending_manager.write_jsonl(
            context.run_id,
            context.run_dir / "pending.jsonl",
        )
        approval_bridge.write_jsonl_for_task(
            context.run_id,
            context.run_dir / "langgraph_interrupts.jsonl",
        )

    def update_state_artifacts(
        self,
        state: VaniScopeGraphState,
        context: WebAgentContext,
        *,
        include_pending: str | None = None,
    ) -> VaniScopeGraphState:
        state["run_dir"] = str(context.run_dir)
        state["artifacts"] = self.list_artifacts(
            context.run_dir,
            include_pending=include_pending,
        )
        return state

    def persist_final_state(
        self,
        state: VaniScopeGraphState,
        context: WebAgentContext,
    ) -> VaniScopeGraphState:
        self.update_state_artifacts(
            state,
            context,
            include_pending="workflow_state.json",
        )
        self.write_workflow_state(state, context.run_dir)
        state["artifacts"] = self.list_artifacts(context.run_dir)
        return state

    def state_after_interrupt(
        self,
        final_state: VaniScopeGraphState,
        *,
        context: WebAgentContext | None,
        thread_id: str | None,
        approval_bridge: LangGraphApprovalBridge,
    ) -> VaniScopeGraphState:
        state = dict(final_state)
        if context is not None:
            state["task_id"] = context.run_id
            state["thread_id"] = thread_id or context.run_id
            state["status"] = "requires_approval"
            state["error"] = context.state.error_message
            self.persist_final_state(state, context)
            approval_bridge.write_jsonl_for_task(
                context.run_id,
                context.run_dir / "langgraph_interrupts.jsonl",
            )
            state["artifacts"] = self.list_artifacts(context.run_dir)
        else:
            state["status"] = "requires_approval"
        return state
