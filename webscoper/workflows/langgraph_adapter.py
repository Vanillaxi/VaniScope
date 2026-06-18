from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, Callable

from webscoper.runtime.context import WebAgentContext
from webscoper.runtime.execution.handler import (
    WebAgentExecutionHandler,
    WebAgentRuntimeComponents,
)
from webscoper.runtime.execution_results import merge_final_output, record_evidence
from webscoper.runtime.execution_state import state_payload, status_from_loop_error
from webscoper.schemas.observation import PageObservation
from webscoper.schemas.plan import ExecutionLoopResult, ExecutionPlan
from webscoper.schemas.prompt import PromptBuildResult
from webscoper.schemas.task import TaskSpec
from webscoper.schemas.tool_call import ToolExecutionRecord
from webscoper.schemas.workflow import (
    LangGraphResumePayload,
    LangGraphResumeResult,
    WorkflowRunResult,
)
from webscoper.workflows.langgraph_approval import LangGraphApprovalBridge
from webscoper.workflows.state import VaniScopeGraphState


TERMINAL_GRAPH_STATUSES = {"failed", "blocked", "requires_approval"}


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
        self.final_observation: PageObservation | None = None
        self.evidence_items: list[Any] = []
        self.report_text: str | None = None
        self._finalized = False
        self._loop: asyncio.AbstractEventLoop | None = None
        self.thread_id: str | None = None
        self._graph: Any | None = None
        self._interrupted = False
        self.approval_bridge = LangGraphApprovalBridge(
            self.handler.approval_store,
            self.handler.pending_manager,
            event_sink=self.handler.event_sink,
        )

    def build_graph(self):
        if self._graph is not None:
            return self._graph
        try:
            from langgraph.graph import END, START, StateGraph
            from langgraph.checkpoint.memory import InMemorySaver
        except ImportError as exc:
            raise RuntimeError(
                "LangGraph workflow requested but langgraph is not installed"
            ) from exc

        graph = StateGraph(VaniScopeGraphState)
        graph.add_node("init_task", self._init_task)
        graph.add_node("build_prompt", self._build_prompt)
        graph.add_node("plan_task", self._plan_task)
        graph.add_node("validate_plan", self._validate_plan)
        graph.add_node("execute_plan", self._execute_plan)
        graph.add_node("build_report", self._build_report)
        graph.add_node("review_report", self._review_report)
        graph.add_node("compact_context", self._compact_context)
        graph.add_node("maybe_revise", self._maybe_revise)
        graph.add_node("finalize_task", self._finalize_task)

        graph.add_edge(START, "init_task")
        graph.add_conditional_edges(
            "init_task",
            _route_to("build_prompt"),
            ["build_prompt", "finalize_task"],
        )
        graph.add_conditional_edges(
            "build_prompt",
            _route_to("plan_task"),
            ["plan_task", "finalize_task"],
        )
        graph.add_conditional_edges(
            "plan_task",
            _route_to("validate_plan"),
            ["validate_plan", "finalize_task"],
        )
        graph.add_conditional_edges(
            "validate_plan",
            _route_to("execute_plan"),
            ["execute_plan", "finalize_task"],
        )
        graph.add_conditional_edges(
            "execute_plan",
            _route_to("build_report"),
            ["build_report", "finalize_task"],
        )
        graph.add_conditional_edges(
            "build_report",
            _route_to("review_report"),
            ["review_report", "finalize_task"],
        )
        graph.add_conditional_edges(
            "review_report",
            _route_to("compact_context"),
            ["compact_context", "finalize_task"],
        )
        graph.add_conditional_edges(
            "compact_context",
            _route_to("maybe_revise"),
            ["maybe_revise", "finalize_task"],
        )
        graph.add_edge("maybe_revise", "finalize_task")
        graph.add_edge("finalize_task", END)
        # Phase 22 intentionally uses an in-memory checkpointer only. This enables
        # single-process interrupt/resume without adding durable storage.
        self._graph = graph.compile(checkpointer=InMemorySaver())
        return self._graph

    def run(self, request: Any) -> WorkflowRunResult:
        task = _coerce_task(request)
        thread_id = task.task_id
        self.thread_id = thread_id
        initial_state: VaniScopeGraphState = {
            "task_id": task.task_id,
            "thread_id": thread_id,
            "task_goal": task.raw_input,
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
                final_state = self._state_after_interrupt(final_state)
        finally:
            if self.runtime is not None and not self._interrupted:
                self._run_async(self.runtime.browser_runtime.close())
            if self._loop is not None and not self._interrupted:
                self._loop.close()
                self._loop = None
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

        graph = self.build_graph()
        config = {"configurable": {"thread_id": thread_id}}
        try:
            final_state = graph.invoke(
                Command(resume=resume_payload.model_dump(mode="json")),
                config=config,
            )
            status = final_state.get("status", "failed")
            if "__interrupt__" in final_state:
                status = "requires_approval"
            if self.context is not None:
                final_state["run_dir"] = str(self.context.run_dir)
                final_state["artifacts"] = _collect_artifacts(
                    self.context.run_dir,
                    include_pending="workflow_state.json",
                )
                _write_workflow_state(
                    self.context.run_dir / "workflow_state.json",
                    final_state,
                )
                final_state["artifacts"] = _collect_artifacts(self.context.run_dir)
                self.approval_bridge.write_jsonl_for_task(
                    task_id,
                    self.context.run_dir / "langgraph_interrupts.jsonl",
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
            if self.context is not None:
                self.context.state.status = "failed"
                self.context.state.error_type = type(exc).__name__
                self.context.state.error_message = str(exc)
                _write_workflow_state(
                    self.context.run_dir / "workflow_state.json",
                    {
                        "task_id": task_id,
                        "thread_id": thread_id,
                        "status": "failed",
                        "error": str(exc),
                        "metadata": {"backend": "langgraph"},
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
            self._interrupted = False
            if self.runtime is not None:
                self._run_async(self.runtime.browser_runtime.close())
            if self._loop is not None:
                self._loop.close()
                self._loop = None

    def _init_task(self, state: VaniScopeGraphState) -> VaniScopeGraphState:
        return self._node(
            "init_task",
            state,
            lambda next_state: self._do_init_task(next_state),
        )

    def _do_init_task(self, state: VaniScopeGraphState) -> VaniScopeGraphState:
        task = TaskSpec.model_validate(state["request"])
        self._emit_workflow_event("workflow_started", {"backend": "langgraph"})
        self.context = self.handler.start_run(task)
        self.runtime = self.handler.build_runtime_components(self.context)
        state["task_id"] = self.context.run_id
        state["thread_id"] = self.thread_id or self.context.run_id
        state["run_dir"] = str(self.context.run_dir)
        return state

    def _build_prompt(self, state: VaniScopeGraphState) -> VaniScopeGraphState:
        return self._node("build_prompt", state, self._do_build_prompt)

    def _do_build_prompt(self, state: VaniScopeGraphState) -> VaniScopeGraphState:
        context = self._require_context()
        self.prompt_result = self.handler.build_prompt(context)
        state["prompt_markdown"] = self.prompt_result.prompt_text
        state["prompt_context"] = self.prompt_result.model_dump(mode="json")
        return state

    def _plan_task(self, state: VaniScopeGraphState) -> VaniScopeGraphState:
        return self._node("plan_task", state, self._do_plan_task)

    def _do_plan_task(self, state: VaniScopeGraphState) -> VaniScopeGraphState:
        context = self._require_context()
        if self.prompt_result is None:
            raise RuntimeError("Prompt result missing before plan_task.")
        self.plan = self._run_async(
            self.handler.plan_task(context, self.prompt_result)
        )
        state["plan"] = self.plan.model_dump(mode="json")
        return state

    def _validate_plan(self, state: VaniScopeGraphState) -> VaniScopeGraphState:
        return self._node("validate_plan", state, self._do_validate_plan)

    def _do_validate_plan(self, state: VaniScopeGraphState) -> VaniScopeGraphState:
        context = self._require_context()
        if self.plan is None:
            raise RuntimeError("Plan missing before validate_plan.")
        try:
            result = self.handler.validate_plan(context, self.plan)
        except RuntimeError as exc:
            state["validation_result"] = _read_json_safe_from_transcript_tail(
                context,
                "plan_validation_completed",
            )
            state["status"] = "failed"
            state["error"] = str(exc)
            return state
        state["validation_result"] = result.model_dump(mode="json")
        return state

    def _execute_plan(self, state: VaniScopeGraphState) -> VaniScopeGraphState:
        return self._node("execute_plan", state, self._do_execute_plan)

    def _do_execute_plan(self, state: VaniScopeGraphState) -> VaniScopeGraphState:
        context = self._require_context()
        runtime = self._require_runtime()
        if self.plan is None:
            raise RuntimeError("Plan missing before execute_plan.")
        self.final_observation = self._run_async(
            self._execute_plan_with_interrupts(context, self.plan, runtime)
        )
        if self.handler.last_loop_result is not None:
            state["execution_result"] = self.handler.last_loop_result.model_dump(
                mode="json"
            )
        state["final_observation"] = self.final_observation.model_dump(mode="json")
        if context.state.status in TERMINAL_GRAPH_STATUSES:
            state["status"] = context.state.status
            state["error"] = context.state.error_message
        return state

    async def _execute_plan_with_interrupts(
        self,
        context: WebAgentContext,
        plan: ExecutionPlan,
        runtime: WebAgentRuntimeComponents,
    ) -> PageObservation:
        try:
            from langgraph.types import interrupt
        except ImportError as exc:
            raise RuntimeError(
                "LangGraph workflow requested but langgraph is not installed"
            ) from exc

        context.transcript_store.append(
            "browser_tool_runtime_started",
            state_payload(context),
        )
        if runtime.browser_runtime.session is None:
            await runtime.browser_runtime.start()
        context.state.current_step = 4
        records: list[ToolExecutionRecord] = []
        final_output: dict[str, Any] = {}

        for index, step in enumerate(plan.steps, start=1):
            if index > context.task.budget.max_steps:
                loop_result = ExecutionLoopResult(
                    task_id=context.task.task_id,
                    status="failed",
                    records=records,
                    final_output=final_output,
                    error_type="MAX_STEPS_EXCEEDED",
                    error_message="Execution plan exceeded task budget max_steps.",
                )
                context.transcript_store.append(
                    "execution_loop_failed",
                    loop_result.model_dump(mode="json"),
                )
                self.handler.last_loop_result = loop_result
                raise RuntimeError(loop_result.error_message)

            context.transcript_store.append(
                "tool_call_started",
                {
                    "step": step.model_dump(mode="json"),
                    "call": step.tool_call.model_dump(mode="json"),
                },
            )
            self._emit_tool_event(
                context,
                "tool_call_started",
                f"Tool call started: {step.tool_call.tool_id}",
                {
                    "step_id": step.step_id,
                    "tool_name": step.tool_call.tool_id,
                    "call_id": step.tool_call.call_id,
                },
            )

            approval_override_id: str | None = None
            risk_result = runtime.tool_executor.risk_gate.check_tool_call(
                task_id=context.run_id,
                tool_name=step.tool_call.tool_id,
                arguments=step.tool_call.arguments,
                page_observation=runtime.browser_runtime.last_observation,
            )
            if risk_result.requires_approval:
                payload = self.approval_bridge.create_interrupt_payload(
                    task_id=context.run_id,
                    thread_id=state_thread_id(context, self.thread_id),
                    tool_name=step.tool_call.tool_id,
                    arguments=step.tool_call.arguments,
                    risk_result=risk_result,
                    node_name="execute_plan",
                    tool_call_id=step.tool_call.call_id,
                    metadata={
                        "context_snapshot": context.snapshot().model_dump(mode="json"),
                        "page_observation": runtime.browser_runtime.last_observation.model_dump(
                            mode="json"
                        )
                        if runtime.browser_runtime.last_observation is not None
                        else None,
                        "call": step.tool_call.model_dump(mode="json"),
                    },
                )
                self._write_approval_artifacts(context)
                context.state.status = "requires_approval"
                context.state.error_type = "RISK_APPROVAL_REQUIRED"
                context.state.error_message = risk_result.reason
                context.transcript_store.append(
                    "approval_required",
                    {"call": step.tool_call.model_dump(mode="json"), "payload": payload},
                )
                context.transcript_store.append(
                    "langgraph_interrupted",
                    {"call": step.tool_call.model_dump(mode="json"), "payload": payload},
                )
                context.transcript_store.append(
                    "task_paused",
                    {"call": step.tool_call.model_dump(mode="json"), "payload": payload},
                )
                resume_payload = interrupt(payload)
                resume = LangGraphResumePayload.model_validate(resume_payload)
                if not resume.approved:
                    context.state.status = "rejected"
                    context.state.error_type = "APPROVAL_REJECTED"
                    context.state.error_message = (
                        resume.reason or "Approval rejected; task will not resume."
                    )
                    pending = self.handler.pending_manager.pop_by_approval_id(
                        resume.approval_id
                    )
                    self._write_approval_artifacts(context)
                    loop_result = ExecutionLoopResult(
                        task_id=context.task.task_id,
                        status="failed",
                        records=records,
                        final_output=final_output,
                        error_type="APPROVAL_REJECTED",
                        error_message=context.state.error_message,
                    )
                    self.handler.last_loop_result = loop_result
                    context.transcript_store.append(
                        "task_rejected",
                        {
                            "approval_id": resume.approval_id,
                            "pending_tool_call": pending.model_dump(mode="json")
                            if pending is not None
                            else None,
                        },
                    )
                    return _require_last_observation(runtime)
                approval_override_id = resume.approval_id
                context.state.status = "resuming"
                context.transcript_store.append(
                    "task_resumed",
                    resume.model_dump(mode="json"),
                )

            tool_result = await runtime.tool_executor.execute(
                step.tool_call,
                context.snapshot(),
                approval_override_id=approval_override_id,
            )
            if approval_override_id is not None:
                self.handler.pending_manager.pop_by_approval_id(approval_override_id)
                self._write_approval_artifacts(context)
            record = ToolExecutionRecord(call=step.tool_call, result=tool_result)
            records.append(record)
            context.transcript_store.append(
                "tool_call_completed",
                record.model_dump(mode="json"),
            )
            if tool_result.error_type == "RISK_BLOCKED":
                context.transcript_store.append(
                    "risk_blocked",
                    {
                        "call": step.tool_call.model_dump(mode="json"),
                        "result": tool_result.model_dump(mode="json"),
                    },
                )
            self._emit_tool_event(
                context,
                "tool_call_finished",
                f"Tool call finished: {step.tool_call.tool_id}",
                {
                    "step_id": step.step_id,
                    "tool_name": step.tool_call.tool_id,
                    "call_id": step.tool_call.call_id,
                    "ok": tool_result.status == "success",
                    "status": tool_result.status,
                    "error_type": tool_result.error_type,
                },
            )
            evidence_item = record_evidence(
                context,
                step.step_id,
                step.tool_call,
                tool_result,
            )
            if evidence_item is not None:
                context.transcript_store.append(
                    "evidence_recorded",
                    evidence_item.model_dump(mode="json"),
                )
                self._emit_tool_event(
                    context,
                    "evidence_added",
                    f"Evidence added: {evidence_item.evidence_id}",
                    {
                        "evidence_id": evidence_item.evidence_id,
                        "kind": evidence_item.kind,
                        "tool_name": step.tool_call.tool_id,
                    },
                )

            merge_final_output(final_output, tool_result.output)

            if tool_result.status in {"failed", "blocked"}:
                loop_result = ExecutionLoopResult(
                    task_id=context.task.task_id,
                    status="failed",
                    records=records,
                    final_output=final_output,
                    error_type=tool_result.error_type,
                    error_message=tool_result.error_message,
                )
                self.handler.last_loop_result = loop_result
                context.transcript_store.append(
                    "execution_loop_failed",
                    loop_result.model_dump(mode="json"),
                )
                runtime_status = status_from_loop_error(loop_result.error_type)
                context.state.status = runtime_status or "failed"
                context.state.error_type = loop_result.error_type
                context.state.error_message = loop_result.error_message
                context.transcript_store.append("execution_failed", state_payload(context))
                if runtime_status == "blocked":
                    self.handler._emit_event(
                        "task_failed",
                        "Task stopped by risk gate",
                        {
                            "run_id": context.run_id,
                            "status": runtime_status,
                            "error_type": loop_result.error_type,
                            "error": loop_result.error_message,
                            "run_dir": str(context.run_dir),
                        },
                    )
                    return _require_last_observation(runtime)
                raise RuntimeError(
                    f"{loop_result.error_type or 'EXECUTION_LOOP_FAILED'}: "
                    f"{loop_result.error_message or 'Execution loop failed.'}"
                )

        loop_result = ExecutionLoopResult(
            task_id=context.task.task_id,
            status="success",
            records=records,
            final_output=final_output,
        )
        self.handler.last_loop_result = loop_result
        context.transcript_store.append(
            "execution_loop_completed",
            loop_result.model_dump(mode="json"),
        )
        observation = runtime.browser_runtime.last_observation
        if observation is None:
            context.state.status = "failed"
            context.state.error_type = "FINAL_OBSERVATION_MISSING"
            context.state.error_message = (
                "Execution loop completed without a final observation."
            )
            context.transcript_store.append("execution_failed", state_payload(context))
            raise RuntimeError(
                "FINAL_OBSERVATION_MISSING: Execution loop completed without a final observation."
            )
        return observation

    def _build_report(self, state: VaniScopeGraphState) -> VaniScopeGraphState:
        return self._node("build_report", state, self._do_build_report)

    def _do_build_report(self, state: VaniScopeGraphState) -> VaniScopeGraphState:
        context = self._require_context()
        if self.final_observation is None:
            raise RuntimeError("Final observation missing before build_report.")
        context.state.status = "completed"
        context.state.current_step = 5
        self.evidence_items, self.report_text = self.handler.build_final_report(
            context,
            self.final_observation,
        )
        state["evidence_items"] = [
            item.model_dump(mode="json") for item in self.evidence_items
        ]
        state["report_markdown"] = self.report_text
        return state

    def _review_report(self, state: VaniScopeGraphState) -> VaniScopeGraphState:
        return self._node("review_report", state, self._do_review_report)

    def _do_review_report(self, state: VaniScopeGraphState) -> VaniScopeGraphState:
        context = self._require_context()
        if self.report_text is None:
            raise RuntimeError("Report text missing before review_report.")
        result = self.handler.review_report(
            context,
            self.report_text,
            self.evidence_items,
        )
        state["review_result"] = result.model_dump(mode="json")
        return state

    def _compact_context(self, state: VaniScopeGraphState) -> VaniScopeGraphState:
        return self._node("compact_context", state, self._do_compact_context)

    def _do_compact_context(self, state: VaniScopeGraphState) -> VaniScopeGraphState:
        context = self._require_context()
        self.handler.compact_context(context)
        state["compaction_result"] = _read_json_file(
            context.run_dir / "compact_context.json"
        )
        return state

    def _maybe_revise(self, state: VaniScopeGraphState) -> VaniScopeGraphState:
        return self._node("maybe_revise", state, self._do_maybe_revise)

    def _do_maybe_revise(self, state: VaniScopeGraphState) -> VaniScopeGraphState:
        context = self._require_context()
        if self.report_text is None:
            raise RuntimeError("Report text missing before maybe_revise.")
        self.handler.maybe_revise_report(
            context,
            self.report_text,
            self.evidence_items,
        )
        state["revise_loop_result"] = _read_json_file(
            context.run_dir / "revise_loop.json"
        )
        return state

    def _finalize_task(self, state: VaniScopeGraphState) -> VaniScopeGraphState:
        return self._node("finalize_task", state, self._do_finalize_task)

    def _do_finalize_task(self, state: VaniScopeGraphState) -> VaniScopeGraphState:
        context = self.context
        if context is not None and not self._finalized:
            status = state.get("status")
            if status not in TERMINAL_GRAPH_STATUSES:
                state["status"] = "succeeded"
                self.handler.finalize_success(context)
            elif status == "failed":
                self.handler.finalize_failure(
                    context,
                    RuntimeError(state.get("error") or "LangGraph workflow failed."),
                )
            self._finalized = True

        if context is not None:
            state["run_dir"] = str(context.run_dir)
            state["artifacts"] = _collect_artifacts(
                context.run_dir,
                include_pending="workflow_state.json",
            )
            _write_workflow_state(context.run_dir / "workflow_state.json", state)
            state["artifacts"] = _collect_artifacts(context.run_dir)

        event_kind = (
            "workflow_failed"
            if state.get("status") in {"failed", "blocked"}
            else "workflow_finished"
        )
        self._emit_workflow_event(
            event_kind,
            {
                "backend": "langgraph",
                "status": state.get("status"),
                "run_dir": state.get("run_dir"),
            },
        )
        return state

    def _node(
        self,
        node_name: str,
        state: VaniScopeGraphState,
        body: Callable[[VaniScopeGraphState], VaniScopeGraphState],
    ) -> VaniScopeGraphState:
        next_state = dict(state)
        self._record_state_event(
            next_state,
            "workflow_node_started",
            {"backend": "langgraph", "node": node_name},
        )
        self._emit_workflow_event(
            "workflow_node_started",
            {"backend": "langgraph", "node": node_name},
        )
        try:
            next_state = body(next_state)
            self._record_state_event(
                next_state,
                "workflow_node_finished",
                {
                    "backend": "langgraph",
                    "node": node_name,
                    "status": next_state.get("status"),
                },
            )
            self._emit_workflow_event(
                "workflow_node_finished",
                {
                    "backend": "langgraph",
                    "node": node_name,
                    "status": next_state.get("status"),
                },
            )
            if node_name == "finalize_task" and self.context is not None:
                _write_workflow_state(
                    self.context.run_dir / "workflow_state.json",
                    next_state,
                )
        except _graph_interrupt_type():
            raise
        except Exception as exc:
            next_state["status"] = "failed"
            next_state["error"] = str(exc)
            if self.context is not None:
                self.context.state.status = "failed"
                self.context.state.error_type = type(exc).__name__
                self.context.state.error_message = str(exc)
            self._record_state_event(
                next_state,
                "workflow_node_finished",
                {
                    "backend": "langgraph",
                    "node": node_name,
                    "status": "failed",
                    "error": str(exc),
                },
            )
            self._emit_workflow_event(
                "workflow_node_finished",
                {
                    "backend": "langgraph",
                    "node": node_name,
                    "status": "failed",
                    "error": str(exc),
                },
            )
        return next_state

    def _emit_workflow_event(self, kind: str, payload: dict[str, Any]) -> None:
        message = kind.replace("_", " ").title()
        self.handler._emit_event(kind, message, payload)

    def _record_state_event(
        self,
        state: VaniScopeGraphState,
        event: str,
        payload: dict[str, Any],
    ) -> None:
        state.setdefault("events", []).append({"event": event, "payload": payload})

    def _require_context(self) -> WebAgentContext:
        if self.context is None:
            raise RuntimeError("Workflow context has not been initialized.")
        return self.context

    def _require_runtime(self) -> WebAgentRuntimeComponents:
        if self.runtime is None:
            raise RuntimeError("Workflow runtime has not been initialized.")
        return self.runtime

    def _run_async(self, awaitable):
        if self._loop is None:
            self._loop = asyncio.new_event_loop()
        return self._loop.run_until_complete(awaitable)

    def _write_approval_artifacts(self, context: WebAgentContext) -> None:
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
        self.approval_bridge.write_jsonl_for_task(
            context.run_id,
            context.run_dir / "langgraph_interrupts.jsonl",
        )

    def _emit_tool_event(
        self,
        context: WebAgentContext,
        kind: str,
        message: str,
        payload: dict[str, Any] | None = None,
    ) -> None:
        event_payload = {"run_id": context.run_id}
        event_payload.update(payload or {})
        self.handler._emit_event(kind, message, event_payload)

    def _state_after_interrupt(
        self,
        final_state: VaniScopeGraphState,
    ) -> VaniScopeGraphState:
        state = dict(final_state)
        context = self.context
        if context is not None:
            state["task_id"] = context.run_id
            state["thread_id"] = self.thread_id or context.run_id
            state["run_dir"] = str(context.run_dir)
            state["status"] = "requires_approval"
            state["error"] = context.state.error_message
            state["artifacts"] = _collect_artifacts(
                context.run_dir,
                include_pending="workflow_state.json",
            )
            _write_workflow_state(context.run_dir / "workflow_state.json", state)
            self.approval_bridge.write_jsonl_for_task(
                context.run_id,
                context.run_dir / "langgraph_interrupts.jsonl",
            )
            state["artifacts"] = _collect_artifacts(context.run_dir)
        else:
            state["status"] = "requires_approval"
        return state


def _route_to(next_node: str):
    def route(state: VaniScopeGraphState) -> str:
        if state.get("status") in TERMINAL_GRAPH_STATUSES:
            return "finalize_task"
        return next_node

    return route


def _coerce_task(request: Any) -> TaskSpec:
    if isinstance(request, TaskSpec):
        return request
    if isinstance(request, dict):
        return TaskSpec.model_validate(request)
    raise TypeError(f"Unsupported workflow request type: {type(request).__name__}")


def state_thread_id(context: WebAgentContext, thread_id: str | None) -> str:
    return thread_id or context.run_id


def _require_last_observation(
    runtime: WebAgentRuntimeComponents,
) -> PageObservation:
    observation = runtime.browser_runtime.last_observation
    if observation is None:
        raise RuntimeError("Execution stopped without a page observation.")
    return observation


def _graph_interrupt_type():
    try:
        from langgraph.errors import GraphInterrupt
    except ImportError:
        return ()
    return GraphInterrupt


def _collect_artifacts(run_dir: Path, include_pending: str | None = None) -> list[str]:
    if not run_dir.exists():
        return []
    artifacts = {path.name for path in run_dir.iterdir() if path.is_file()}
    if include_pending is not None:
        artifacts.add(include_pending)
    return sorted(artifacts)


def _write_workflow_state(path: Path, state: VaniScopeGraphState) -> None:
    path.write_text(
        json.dumps(_json_safe(state), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def _read_json_file(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _read_json_safe_from_transcript_tail(
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


def _json_safe(value: Any) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=False, default=str))
