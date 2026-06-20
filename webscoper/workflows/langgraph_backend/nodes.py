from __future__ import annotations

from typing import Any, Callable

from webscoper.runtime.execution.context import WebAgentContext
from webscoper.runtime.execution.handler import WebAgentRuntimeComponents
from webscoper.runtime.llm.auto_explore import (
    AutoExploreActionPlanner,
    decision_to_tool_call,
)
from webscoper.runtime.llm.router import LLMProviderRouter
from webscoper.runtime.execution.results import merge_final_output, record_evidence
from webscoper.runtime.execution.state import state_payload, status_from_loop_error
from webscoper.schemas.browser import PageObservation
from webscoper.schemas.runtime import SkillPromptContext
from webscoper.schemas.tool import ExecutionLoopResult, ExecutionPlan
from webscoper.schemas.task import TaskSpec
from webscoper.schemas.tool import ToolCall, ToolExecutionRecord, ToolResult
from webscoper.tools.gateway import ToolInvocationRequest, ToolInvocationResult
from webscoper.schemas.workflow import LangGraphResumePayload
from webscoper.skills.router import SkillRouter
from webscoper.workflows.langgraph_backend.state_io import (
    TERMINAL_GRAPH_STATUSES,
    graph_interrupt_type,
    read_json_file,
    read_json_safe_from_transcript_tail,
    state_thread_id,
)
from webscoper.workflows.state import VaniScopeGraphState


class LangGraphWorkflowNodes:
    def __init__(self, workflow: Any) -> None:
        self.workflow = workflow

    def init_task(self, state: VaniScopeGraphState) -> VaniScopeGraphState:
        return self._node(
            "init_task",
            state,
            lambda next_state: self._do_init_task(next_state),
        )

    def _do_init_task(self, state: VaniScopeGraphState) -> VaniScopeGraphState:
        task = TaskSpec.model_validate(state["request"])
        self.workflow.event_emitter.emit_workflow_event(
            "workflow_started",
            {"backend": "langgraph"},
        )
        self.workflow.context = self.workflow.handler.start_run(task)
        self.workflow.runtime = self.workflow.handler.build_runtime_components(
            self.workflow.context
        )
        state["task_id"] = self.workflow.context.run_id
        state["thread_id"] = self.workflow.thread_id or self.workflow.context.run_id
        state["run_dir"] = str(self.workflow.context.run_dir)
        return state

    def route_skill(self, state: VaniScopeGraphState) -> VaniScopeGraphState:
        return self._node("route_skill", state, self._do_route_skill)

    def _do_route_skill(self, state: VaniScopeGraphState) -> VaniScopeGraphState:
        context = self.workflow.require_context()
        route = SkillRouter().route(context.task)
        context.task = route.task
        state["request"] = route.task.model_dump(mode="json")
        state["task_type"] = route.task.task_type
        state["skill_id"] = route.task.skill_id

        if route.skill is None:
            self.workflow.skill = None
            self.workflow.skill_plan = None
            context.skill_context = None
            state["skill_context"] = None
            state["skill_plan"] = None
        else:
            skill_input = route.skill.build_input(route.task)
            skill_plan = route.skill.plan(skill_input)
            skill_context = SkillPromptContext(
                skill_id=route.skill.definition.skill_id,
                name=route.skill.definition.name,
                description=route.skill.definition.description,
                version=route.skill.definition.version,
                instruction=route.skill.definition.instruction.content,
                plan=skill_plan.model_dump(mode="json"),
            )
            self.workflow.skill = route.skill
            self.workflow.skill_plan = skill_plan
            context.skill_context = skill_context
            state["skill_context"] = skill_context.model_dump(mode="json")
            state["skill_plan"] = skill_plan.model_dump(mode="json")
            context.version.skill_version = (
                f"{route.skill.definition.skill_id}@{route.skill.definition.version}"
            )

        context.transcript_store.append(
            "skill_routed",
            {
                "reason": route.reason,
                "skill_id": route.task.skill_id,
                "task_type": route.task.task_type,
                "skill_plan": state.get("skill_plan"),
            },
        )
        return state

    def build_prompt(self, state: VaniScopeGraphState) -> VaniScopeGraphState:
        return self._node("build_prompt", state, self._do_build_prompt)

    def _do_build_prompt(self, state: VaniScopeGraphState) -> VaniScopeGraphState:
        context = self.workflow.require_context()
        self.workflow.prompt_result = self.workflow.handler.build_prompt(context)
        state["prompt_markdown"] = self.workflow.prompt_result.prompt_text
        state["prompt_context"] = self.workflow.prompt_result.model_dump(mode="json")
        if self.workflow.handler.dry_run:
            self.workflow.handler.persist_dry_run_result(
                context,
                self.workflow.prompt_result,
            )
            state["dry_run_complete"] = True
        return state

    def plan_task(self, state: VaniScopeGraphState) -> VaniScopeGraphState:
        return self._node("plan_task", state, self._do_plan_task)

    def _do_plan_task(self, state: VaniScopeGraphState) -> VaniScopeGraphState:
        context = self.workflow.require_context()
        if self.workflow.prompt_result is None:
            raise RuntimeError("Prompt result missing before plan_task.")
        self.workflow.plan = self.workflow.run_async(
            self.workflow.handler.plan_task(context, self.workflow.prompt_result)
        )
        state["plan"] = self.workflow.plan.model_dump(mode="json")
        return state

    def validate_plan(self, state: VaniScopeGraphState) -> VaniScopeGraphState:
        return self._node("validate_plan", state, self._do_validate_plan)

    def _do_validate_plan(self, state: VaniScopeGraphState) -> VaniScopeGraphState:
        context = self.workflow.require_context()
        if self.workflow.plan is None:
            raise RuntimeError("Plan missing before validate_plan.")
        try:
            result = self.workflow.handler.validate_plan(
                context,
                self.workflow.plan,
                self.workflow.require_runtime().tool_gateway,
            )
        except RuntimeError as exc:
            state["validation_result"] = read_json_safe_from_transcript_tail(
                context,
                "plan_validation_completed",
            )
            state["status"] = "failed"
            state["error"] = str(exc)
            return state
        state["validation_result"] = result.model_dump(mode="json")
        return state

    def execute_plan(self, state: VaniScopeGraphState) -> VaniScopeGraphState:
        return self._node("execute_plan", state, self._do_execute_plan)

    def _do_execute_plan(self, state: VaniScopeGraphState) -> VaniScopeGraphState:
        context = self.workflow.require_context()
        runtime = self.workflow.require_runtime()
        if self.workflow.plan is None:
            raise RuntimeError("Plan missing before execute_plan.")
        if context.task.mode == "auto_explore" and context.task.task_type == "browser_task":
            self.workflow.final_observation = self.workflow.run_async(
                self._execute_auto_explore_with_interrupts(
                    context,
                    self.workflow.plan,
                    runtime,
                )
            )
        else:
            self.workflow.final_observation = self.workflow.run_async(
                self._execute_plan_with_interrupts(context, self.workflow.plan, runtime)
            )
        if self.workflow.handler.last_loop_result is not None:
            state["execution_result"] = (
                self.workflow.handler.last_loop_result.model_dump(mode="json")
            )
        state["final_observation"] = self.workflow.final_observation.model_dump(
            mode="json"
        )
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
                self.workflow.handler.last_loop_result = loop_result
                raise RuntimeError(loop_result.error_message)

            context.transcript_store.append(
                "tool_call_started",
                {
                    "step": step.model_dump(mode="json"),
                    "call": step.tool_call.model_dump(mode="json"),
                },
            )
            self.workflow.event_emitter.emit_tool_event(
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
            gateway_request = _gateway_request(
                context=context,
                runtime=runtime,
                tool_name=step.tool_call.tool_id,
                arguments=step.tool_call.arguments,
                call_id=step.tool_call.call_id,
                workflow_backend="langgraph",
            )
            gateway_result = await runtime.tool_gateway.invoke(gateway_request)
            if gateway_result.status == "approval_required":
                payload = self.workflow.approval_bridge.create_interrupt_payload(
                    task_id=context.run_id,
                    thread_id=state_thread_id(context, self.workflow.thread_id),
                    tool_name=step.tool_call.tool_id,
                    arguments=step.tool_call.arguments,
                    risk_result=gateway_result.output.get("risk_check"),
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
                self.workflow.artifact_writer.write_approval_artifacts(
                    context,
                    self.workflow.approval_bridge,
                )
                context.state.status = "requires_approval"
                context.state.error_type = "RISK_APPROVAL_REQUIRED"
                context.state.error_message = (
                    gateway_result.error_message or "Approval required before tool execution."
                )
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
                    pending = self.workflow.handler.pending_manager.pop_by_approval_id(
                        resume.approval_id
                    )
                    self.workflow.artifact_writer.write_approval_artifacts(
                        context,
                        self.workflow.approval_bridge,
                    )
                    loop_result = ExecutionLoopResult(
                        task_id=context.task.task_id,
                        status="failed",
                        records=records,
                        final_output=final_output,
                        error_type="APPROVAL_REJECTED",
                        error_message=context.state.error_message,
                    )
                    self.workflow.handler.last_loop_result = loop_result
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

                resumed_request = gateway_request.model_copy(
                    update={"approval_override_id": approval_override_id}
                )
                gateway_result = await runtime.tool_gateway.invoke(resumed_request)

            tool_result = _tool_result_from_gateway(gateway_result)
            if approval_override_id is not None:
                self.workflow.handler.pending_manager.pop_by_approval_id(
                    approval_override_id
                )
                self.workflow.artifact_writer.write_approval_artifacts(
                    context,
                    self.workflow.approval_bridge,
                )
            record = ToolExecutionRecord(call=step.tool_call, result=tool_result)
            records.append(record)
            context.transcript_store.append(
                "tool_call_completed",
                record.model_dump(mode="json"),
            )
            if tool_result.status == "blocked":
                risk_payload = {
                    "run_id": context.run_id,
                    "tool_name": step.tool_call.tool_id,
                    "call": step.tool_call.model_dump(mode="json"),
                    "result": tool_result.model_dump(mode="json"),
                }
                context.transcript_store.append("risk_blocked", risk_payload)
                self.workflow.handler._emit_event(
                    "risk_blocked",
                    "Risk gate blocked tool execution",
                    risk_payload,
                )
            self.workflow.event_emitter.emit_tool_event(
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
                self.workflow.event_emitter.emit_tool_event(
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
                self.workflow.handler.last_loop_result = loop_result
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
                    self.workflow.handler._emit_event(
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
        self.workflow.handler.last_loop_result = loop_result
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

    async def _execute_auto_explore_with_interrupts(
        self,
        context: WebAgentContext,
        seed_plan: ExecutionPlan,
        runtime: WebAgentRuntimeComponents,
    ) -> PageObservation:
        context.transcript_store.append(
            "browser_tool_runtime_started",
            state_payload(context),
        )
        context.state.current_step = 4
        records: list[ToolExecutionRecord] = []
        final_output: dict[str, Any] = {}
        history: list[dict[str, Any]] = []

        for step in seed_plan.steps:
            tool_result = await self._invoke_auto_tool(context, runtime, step.tool_call)
            record = ToolExecutionRecord(call=step.tool_call, result=tool_result)
            records.append(record)
            history.append(_history_item(step.tool_call, tool_result))
            merge_final_output(final_output, tool_result.output)
            evidence_item = record_evidence(context, step.step_id, step.tool_call, tool_result)
            if evidence_item is not None:
                context.transcript_store.append(
                    "evidence_recorded",
                    evidence_item.model_dump(mode="json"),
                )
            if tool_result.status in {"failed", "blocked"}:
                return self._finish_auto_explore_failure(
                    context,
                    runtime,
                    records,
                    final_output,
                    tool_result.error_type,
                    tool_result.error_message,
                )

        planner = AutoExploreActionPlanner(
            self._auto_explore_llm_client(context),
            repair_attempts=self.workflow.handler.repair_attempts,
        )

        for step_index in range(len(records) + 1, context.task.budget.max_steps + 1):
            try:
                decision = await planner.decide(
                    context=context.snapshot(),
                    observation=runtime.browser_runtime.last_observation,
                    history=history,
                    step_index=step_index,
                )
            except RuntimeError as exc:
                context.transcript_store.append(
                    "auto_explore_validation_failed",
                    {"error": str(exc), "step_index": step_index},
                )
                return self._finish_auto_explore_failure(
                    context,
                    runtime,
                    records,
                    final_output,
                    "LLM_ACTION_SCHEMA_INVALID",
                    str(exc),
                )

            context.transcript_store.append(
                "auto_explore_decision",
                decision.model_dump(mode="json"),
            )
            self.workflow.handler._emit_event(
                "planner_finished",
                "Auto explore action selected",
                {
                    "run_id": context.run_id,
                    "step_index": step_index,
                    "action_type": decision.action.type,
                    "target_hint": decision.action.target_hint,
                },
            )

            try:
                tool_call = decision_to_tool_call(decision, f"auto_call_{step_index:03d}")
            except RuntimeError as exc:
                return self._finish_auto_explore_failure(
                    context,
                    runtime,
                    records,
                    final_output,
                    "LLM_ACTION_SCHEMA_INVALID",
                    str(exc),
                )

            tool_result = await self._invoke_auto_tool(context, runtime, tool_call)
            record = ToolExecutionRecord(call=tool_call, result=tool_result)
            records.append(record)
            history.append(_history_item(tool_call, tool_result))
            merge_final_output(final_output, tool_result.output)
            evidence_item = record_evidence(
                context,
                f"auto_step_{step_index:03d}",
                tool_call,
                tool_result,
            )
            if evidence_item is not None:
                context.transcript_store.append(
                    "evidence_recorded",
                    evidence_item.model_dump(mode="json"),
                )
                self.workflow.event_emitter.emit_tool_event(
                    context,
                    "evidence_added",
                    f"Evidence added: {evidence_item.evidence_id}",
                    {
                        "evidence_id": evidence_item.evidence_id,
                        "kind": evidence_item.kind,
                        "tool_name": tool_call.tool_id,
                    },
                )

            if tool_result.error_type == "RISK_APPROVAL_REQUIRED":
                context.state.status = "requires_approval"
                context.state.error_type = tool_result.error_type
                context.state.error_message = tool_result.error_message
                self.workflow.handler.last_loop_result = ExecutionLoopResult(
                    task_id=context.task.task_id,
                    status="failed",
                    records=records,
                    final_output=final_output,
                    error_type=tool_result.error_type,
                    error_message=tool_result.error_message,
                )
                context.transcript_store.append("task_paused", _state_payload(context))
                return _require_last_observation(runtime)

            if tool_result.status in {"failed", "blocked"}:
                return self._finish_auto_explore_failure(
                    context,
                    runtime,
                    records,
                    final_output,
                    tool_result.error_type,
                    tool_result.error_message,
                )

            if tool_call.tool_id == "finish_task":
                loop_result = ExecutionLoopResult(
                    task_id=context.task.task_id,
                    status="success",
                    records=records,
                    final_output=final_output,
                )
                self.workflow.handler.last_loop_result = loop_result
                context.transcript_store.append(
                    "execution_loop_completed",
                    loop_result.model_dump(mode="json"),
                )
                return _require_last_observation(runtime)

        return self._finish_auto_explore_failure(
            context,
            runtime,
            records,
            final_output,
            "MAX_STEPS_EXCEEDED",
            "auto_explore exceeded task budget max_steps.",
        )

    async def _invoke_auto_tool(
        self,
        context: WebAgentContext,
        runtime: WebAgentRuntimeComponents,
        tool_call: ToolCall,
    ) -> ToolResult:
        context.transcript_store.append(
            "tool_call_started",
            {"call": tool_call.model_dump(mode="json")},
        )
        self.workflow.event_emitter.emit_tool_event(
            context,
            "tool_call_started",
            f"Tool call started: {tool_call.tool_id}",
            {
                "step_id": tool_call.call_id,
                "tool_name": tool_call.tool_id,
                "call_id": tool_call.call_id,
            },
        )
        gateway_result = await runtime.tool_gateway.invoke(
            _gateway_request(
                context=context,
                runtime=runtime,
                tool_name=tool_call.tool_id,
                arguments=tool_call.arguments,
                call_id=tool_call.call_id,
                workflow_backend="langgraph",
            )
        )
        tool_result = _tool_result_from_gateway(gateway_result)
        record = ToolExecutionRecord(call=tool_call, result=tool_result)
        context.transcript_store.append(
            "tool_call_completed",
            record.model_dump(mode="json"),
        )
        self.workflow.event_emitter.emit_tool_event(
            context,
            "tool_call_finished",
            f"Tool call finished: {tool_call.tool_id}",
            {
                "step_id": tool_call.call_id,
                "tool_name": tool_call.tool_id,
                "call_id": tool_call.call_id,
                "ok": tool_result.status == "success",
                "status": tool_result.status,
                "error_type": tool_result.error_type,
            },
        )
        return tool_result

    def _finish_auto_explore_failure(
        self,
        context: WebAgentContext,
        runtime: WebAgentRuntimeComponents,
        records: list[ToolExecutionRecord],
        final_output: dict[str, Any],
        error_type: str | None,
        error_message: str | None,
    ) -> PageObservation:
        loop_result = ExecutionLoopResult(
            task_id=context.task.task_id,
            status="failed",
            records=records,
            final_output=final_output,
            error_type=error_type,
            error_message=error_message,
        )
        self.workflow.handler.last_loop_result = loop_result
        context.transcript_store.append(
            "execution_loop_failed",
            loop_result.model_dump(mode="json"),
        )
        runtime_status = status_from_loop_error(error_type)
        context.state.status = runtime_status or "failed"
        context.state.error_type = error_type
        context.state.error_message = error_message
        context.transcript_store.append("execution_failed", state_payload(context))
        if runtime.browser_runtime.last_observation is not None and runtime_status is not None:
            return runtime.browser_runtime.last_observation
        return _require_last_observation(runtime)

    def _auto_explore_llm_client(self, context: WebAgentContext):
        if self.workflow.handler.planner_mode in {"fake_llm", "real_llm"}:
            return self.workflow.handler._create_llm_client(context, purpose="auto_explore")
        return LLMProviderRouter(None).create_client(
            run_dir=context.run_dir,
            task_id=context.run_id,
            purpose="auto_explore",
            budget=context.task.budget,
        )

    def build_report(self, state: VaniScopeGraphState) -> VaniScopeGraphState:
        return self._node("build_report", state, self._do_build_report)

    def _do_build_report(self, state: VaniScopeGraphState) -> VaniScopeGraphState:
        context = self.workflow.require_context()
        if self.workflow.final_observation is None:
            raise RuntimeError("Final observation missing before build_report.")
        context.state.status = "completed"
        context.state.current_step = 5
        self.workflow.evidence_items, self.workflow.report_text = (
            self.workflow.handler.build_final_report(
                context,
                self.workflow.final_observation,
            )
        )
        state["evidence_items"] = [
            item.model_dump(mode="json") for item in self.workflow.evidence_items
        ]
        state["report_markdown"] = self.workflow.report_text
        return state

    def review_report(self, state: VaniScopeGraphState) -> VaniScopeGraphState:
        return self._node("review_report", state, self._do_review_report)

    def _do_review_report(self, state: VaniScopeGraphState) -> VaniScopeGraphState:
        context = self.workflow.require_context()
        if self.workflow.report_text is None:
            raise RuntimeError("Report text missing before review_report.")
        result = self.workflow.handler.review_report(
            context,
            self.workflow.report_text,
            self.workflow.evidence_items,
        )
        state["review_result"] = result.model_dump(mode="json")
        return state

    def compact_context(self, state: VaniScopeGraphState) -> VaniScopeGraphState:
        return self._node("compact_context", state, self._do_compact_context)

    def _do_compact_context(self, state: VaniScopeGraphState) -> VaniScopeGraphState:
        context = self.workflow.require_context()
        self.workflow.handler.compact_context(context)
        state["compaction_result"] = read_json_file(
            context.run_dir / "compact_context.json"
        )
        return state

    def maybe_revise(self, state: VaniScopeGraphState) -> VaniScopeGraphState:
        return self._node("maybe_revise", state, self._do_maybe_revise)

    def _do_maybe_revise(self, state: VaniScopeGraphState) -> VaniScopeGraphState:
        context = self.workflow.require_context()
        if self.workflow.report_text is None:
            raise RuntimeError("Report text missing before maybe_revise.")
        self.workflow.handler.maybe_revise_report(
            context,
            self.workflow.report_text,
            self.workflow.evidence_items,
        )
        state["revise_loop_result"] = read_json_file(
            context.run_dir / "revise_loop.json"
        )
        return state

    def finalize_task(self, state: VaniScopeGraphState) -> VaniScopeGraphState:
        return self._node("finalize_task", state, self._do_finalize_task)

    def _do_finalize_task(self, state: VaniScopeGraphState) -> VaniScopeGraphState:
        context = self.workflow.context
        if context is not None and not self.workflow.finalized:
            status = state.get("status")
            if status not in TERMINAL_GRAPH_STATUSES:
                state["status"] = "succeeded"
                self.workflow.handler.finalize_success(context)
            elif status == "failed":
                self.workflow.handler.finalize_failure(
                    context,
                    RuntimeError(state.get("error") or "LangGraph workflow failed."),
                )
            self.workflow.finalized = True

        if context is not None:
            self.workflow.artifact_writer.persist_final_state(state, context)

        event_kind = (
            "workflow_failed"
            if state.get("status") in {"failed", "blocked"}
            else "workflow_finished"
        )
        self.workflow.event_emitter.emit_workflow_event(
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
        self.workflow.event_emitter.emit_node_started(next_state, node_name)
        try:
            next_state = body(next_state)
            self.workflow.event_emitter.emit_node_finished(
                next_state,
                node_name,
                status=next_state.get("status"),
            )
            if node_name == "finalize_task" and self.workflow.context is not None:
                self.workflow.artifact_writer.write_workflow_state(
                    next_state,
                    self.workflow.context.run_dir,
                )
        except graph_interrupt_type():
            raise
        except Exception as exc:
            next_state["status"] = "failed"
            next_state["error"] = str(exc)
            if self.workflow.context is not None:
                self.workflow.context.state.status = "failed"
                self.workflow.context.state.error_type = type(exc).__name__
                self.workflow.context.state.error_message = str(exc)
            self.workflow.event_emitter.emit_node_finished(
                next_state,
                node_name,
                status="failed",
                error=str(exc),
            )
        return next_state


def _require_last_observation(
    runtime: WebAgentRuntimeComponents,
) -> PageObservation:
    observation = runtime.browser_runtime.last_observation
    if observation is None:
        raise RuntimeError("Execution stopped without a page observation.")
    return observation


def _gateway_request(
    *,
    context: WebAgentContext,
    runtime: WebAgentRuntimeComponents,
    tool_name: str,
    arguments: dict[str, Any],
    call_id: str,
    workflow_backend: str,
) -> ToolInvocationRequest:
    return ToolInvocationRequest(
        task_id=context.run_id,
        tool_name=tool_name,
        arguments=arguments,
        call_id=call_id,
        workflow_backend=workflow_backend,
        run_dir=str(context.run_dir),
        context_snapshot=context.snapshot().model_dump(mode="json"),
        page_observation=runtime.browser_runtime.last_observation.model_dump(mode="json")
        if runtime.browser_runtime.last_observation is not None
        else None,
    )


def _tool_result_from_gateway(result: ToolInvocationResult) -> ToolResult:
    status = "blocked" if result.status == "approval_required" else result.status
    return ToolResult(
        call_id=result.call_id or "gateway_call",
        tool_id=result.tool_name,
        status=status,
        output=result.output,
        error_type=result.error_type,
        error_message=result.error_message,
        started_at=result.started_at,
        ended_at=result.ended_at,
    )


def _history_item(tool_call: ToolCall, tool_result: ToolResult) -> dict[str, Any]:
    return {
        "tool_id": tool_call.tool_id,
        "action_type": tool_call.tool_id,
        "target_hint": _action_target_hint(tool_call),
        "status": tool_result.status,
        "error_type": tool_result.error_type,
        "error_message": tool_result.error_message,
    }


def _action_target_hint(tool_call: ToolCall) -> str | None:
    action = tool_call.arguments.get("action")
    if not isinstance(action, dict):
        return None
    target_hint = action.get("target_hint")
    return str(target_hint) if target_hint is not None else None
