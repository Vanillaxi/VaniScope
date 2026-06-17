from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, Callable

from webscoper.runtime.context import WebAgentContext
from webscoper.runtime.execution import (
    WebAgentExecutionHandler,
    WebAgentRuntimeComponents,
)
from webscoper.schemas.observation import PageObservation
from webscoper.schemas.plan import ExecutionPlan
from webscoper.schemas.prompt import PromptBuildResult
from webscoper.schemas.task import TaskSpec
from webscoper.schemas.workflow import WorkflowRunResult
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

    def build_graph(self):
        try:
            from langgraph.graph import END, START, StateGraph
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
        return graph.compile()

    def run(self, request: Any) -> WorkflowRunResult:
        task = _coerce_task(request)
        initial_state: VaniScopeGraphState = {
            "task_id": task.task_id,
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
        try:
            final_state = graph.invoke(initial_state)
        finally:
            if self.runtime is not None:
                self._run_async(self.runtime.browser_runtime.close())
            if self._loop is not None:
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
            self.handler.execute_plan(context, self.plan, runtime)
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
