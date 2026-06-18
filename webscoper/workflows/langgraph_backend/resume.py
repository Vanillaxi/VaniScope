from __future__ import annotations

from typing import Any, Callable

from webscoper.runtime.context import WebAgentContext
from webscoper.schemas.workflow import LangGraphResumePayload, LangGraphResumeResult
from webscoper.workflows.langgraph_approval import LangGraphApprovalBridge
from webscoper.workflows.langgraph_backend.artifacts import WorkflowArtifactWriter
from webscoper.workflows.langgraph_backend.events import WorkflowEventEmitter


class LangGraphResumeHandler:
    def __init__(
        self,
        *,
        compiled_graph: Any,
        context_getter: Callable[[], WebAgentContext | None],
        approval_bridge: LangGraphApprovalBridge,
        artifact_writer: WorkflowArtifactWriter,
        event_emitter: WorkflowEventEmitter,
        cleanup: Callable[[], None],
    ) -> None:
        self.compiled_graph = compiled_graph
        self.context_getter = context_getter
        self.approval_bridge = approval_bridge
        self.artifact_writer = artifact_writer
        self.event_emitter = event_emitter
        self.cleanup = cleanup

    def resume(
        self,
        *,
        task_id: str,
        thread_id: str,
        resume_payload: LangGraphResumePayload,
    ) -> LangGraphResumeResult:
        try:
            from langgraph.types import Command
        except ImportError as exc:
            return LangGraphResumeResult(
                task_id=task_id,
                approval_id=resume_payload.approval_id,
                resumed=False,
                status="failed",
                message="LangGraph is not installed.",
                error=str(exc),
            )

        config = {"configurable": {"thread_id": thread_id}}
        try:
            final_state = self.compiled_graph.invoke(
                Command(resume=resume_payload.model_dump(mode="json")),
                config=config,
            )
            status = final_state.get("status", "failed")
            if "__interrupt__" in final_state:
                status = "requires_approval"
            context = self.context_getter()
            if context is not None:
                self.artifact_writer.update_state_artifacts(
                    final_state,
                    context,
                    include_pending="workflow_state.json",
                )
                self.artifact_writer.write_workflow_state(final_state, context.run_dir)
                final_state["artifacts"] = self.artifact_writer.list_artifacts(
                    context.run_dir
                )
                self.approval_bridge.write_jsonl_for_task(
                    task_id,
                    context.run_dir / "langgraph_interrupts.jsonl",
                )
            self.event_emitter.emit_workflow_event(
                "langgraph_resumed",
                {
                    "backend": "langgraph",
                    "task_id": task_id,
                    "thread_id": thread_id,
                    "status": status,
                },
            )
            return LangGraphResumeResult(
                task_id=task_id,
                approval_id=resume_payload.approval_id,
                resumed=status == "succeeded",
                status=status,
                message=(
                    "LangGraph task resumed and finished."
                    if status == "succeeded"
                    else "LangGraph task resumed."
                ),
                error=final_state.get("error"),
                metadata={
                    "thread_id": thread_id,
                    "artifacts": final_state.get("artifacts", []),
                },
            )
        except Exception as exc:
            context = self.context_getter()
            if context is not None:
                context.state.status = "failed"
                context.state.error_type = type(exc).__name__
                context.state.error_message = str(exc)
                self.artifact_writer.write_workflow_state(
                    {
                        "task_id": task_id,
                        "thread_id": thread_id,
                        "status": "failed",
                        "error": str(exc),
                        "metadata": {"backend": "langgraph"},
                    },
                    context.run_dir,
                )
            self.event_emitter.emit_workflow_event(
                "langgraph_resume_failed",
                {
                    "backend": "langgraph",
                    "task_id": task_id,
                    "thread_id": thread_id,
                    "error": str(exc),
                },
            )
            return LangGraphResumeResult(
                task_id=task_id,
                approval_id=resume_payload.approval_id,
                resumed=False,
                status="failed",
                message="LangGraph resume failed.",
                error=str(exc),
                metadata={"thread_id": thread_id},
            )
        finally:
            self.cleanup()
