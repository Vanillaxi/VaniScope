from __future__ import annotations

import asyncio
from typing import Any

from webscoper.runtime.execution.context import WebAgentContext
from webscoper.runtime.execution.handler import (
    WebAgentExecutionHandler,
    WebAgentRuntimeComponents,
)
from webscoper.schemas.browser import PageObservation
from webscoper.schemas.tool import ExecutionPlan
from webscoper.schemas.runtime import PromptBuildResult
from webscoper.schemas.workflow import (
    LangGraphResumePayload,
    LangGraphResumeResult,
    WorkflowRunResult,
)
from webscoper.skills.base import Skill, SkillPlan
from webscoper.workflows.langgraph_approval import LangGraphApprovalBridge
from webscoper.workflows.langgraph_backend.artifacts import WorkflowArtifactWriter
from webscoper.workflows.langgraph_backend.events import WorkflowEventEmitter
from webscoper.workflows.langgraph_backend.graph import build_langgraph_workflow
from webscoper.workflows.langgraph_backend.nodes import LangGraphWorkflowNodes
from webscoper.workflows.langgraph_backend.resume import LangGraphResumeHandler
from webscoper.workflows.langgraph_backend.state_io import coerce_task
from webscoper.workflows.state import VaniScopeGraphState


class LangGraphWorkflowAdapter:
    def __init__(
        self,
        task_runner_components: WebAgentExecutionHandler,
        event_sink: Any | None = None,
    ) -> None:
        self.handler = task_runner_components
        if event_sink is not None:
            self.handler.event_sink = event_sink
        self.context: WebAgentContext | None = None
        self.runtime: WebAgentRuntimeComponents | None = None
        self.prompt_result: PromptBuildResult | None = None
        self.plan: ExecutionPlan | None = None
        self.skill: Skill | None = None
        self.skill_plan: SkillPlan | None = None
        self.final_observation: PageObservation | None = None
        self.evidence_items: list[Any] = []
        self.report_text: str | None = None
        self.finalized = False
        self._loop: asyncio.AbstractEventLoop | None = None
        self.thread_id: str | None = None
        self._graph: Any | None = None
        self._interrupted = False
        self.approval_bridge = LangGraphApprovalBridge(
            self.handler.approval_store,
            self.handler.pending_manager,
            event_sink=self.handler.event_sink,
        )
        self.artifact_writer = WorkflowArtifactWriter(self.handler)
        self.event_emitter = WorkflowEventEmitter(self.handler)
        self.nodes = LangGraphWorkflowNodes(self)

    def build_graph(self):
        if self._graph is None:
            self._graph = build_langgraph_workflow(nodes=self.nodes)
        return self._graph

    def run(self, request: Any) -> WorkflowRunResult:
        task = coerce_task(request)
        thread_id = task.task_id
        self.thread_id = thread_id
        initial_state: VaniScopeGraphState = {
            "task_id": task.task_id,
            "thread_id": thread_id,
            "task_goal": task.raw_input,
            "task_type": task.task_type,
            "skill_id": task.skill_id,
            "request": task.model_dump(mode="json"),
            "workspace": str(self.handler.workspace)
            if self.handler.workspace is not None
            else None,
            "planner_mode": self.handler.planner_mode,
            "status": "running",
            "artifacts": [],
            "events": [],
            "metadata": {"backend": "langgraph"},
            "error": None,
        }
        graph = self.build_graph()
        config = {"configurable": {"thread_id": thread_id}}
        try:
            final_state = graph.invoke(initial_state, config=config)
            if "__interrupt__" in final_state:
                self._interrupted = True
                final_state = self.artifact_writer.state_after_interrupt(
                    final_state,
                    context=self.context,
                    thread_id=self.thread_id,
                    approval_bridge=self.approval_bridge,
                )
        finally:
            if not self._interrupted:
                self.cleanup()
        return WorkflowRunResult(
            task_id=final_state.get("task_id", task.task_id),
            backend="langgraph",
            status=final_state.get("status", "failed"),
            run_dir=final_state.get("run_dir"),
            artifacts=final_state.get("artifacts", []),
            error=final_state.get("error"),
            metadata=final_state.get("metadata", {}),
        )

    def resume(
        self,
        *,
        task_id: str,
        thread_id: str,
        resume_payload: LangGraphResumePayload,
    ) -> LangGraphResumeResult:
        self._interrupted = False
        handler = LangGraphResumeHandler(
            compiled_graph=self.build_graph(),
            context_getter=lambda: self.context,
            approval_bridge=self.approval_bridge,
            artifact_writer=self.artifact_writer,
            event_emitter=self.event_emitter,
            cleanup=self.cleanup,
        )
        return handler.resume(
            task_id=task_id,
            thread_id=thread_id,
            resume_payload=resume_payload,
        )

    def require_context(self) -> WebAgentContext:
        if self.context is None:
            raise RuntimeError("Workflow context has not been initialized.")
        return self.context

    def require_runtime(self) -> WebAgentRuntimeComponents:
        if self.runtime is None:
            raise RuntimeError("Workflow runtime has not been initialized.")
        return self.runtime

    def run_async(self, awaitable):
        if self._loop is None:
            self._loop = asyncio.new_event_loop()
        return self._loop.run_until_complete(awaitable)

    def cleanup(self) -> None:
        self._interrupted = False
        if self.runtime is not None:
            self.run_async(self.runtime.browser_runtime.close())
        if self._loop is not None:
            self._loop.close()
            self._loop = None
