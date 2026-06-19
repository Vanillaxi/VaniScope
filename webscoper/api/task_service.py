from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from webscoper.api.approvals import decide_approval as decide_approval_for_service
from webscoper.api.artifacts import (
    ARTIFACT_ALLOWLIST,
    list_existing_artifacts,
    list_task_artifacts,
    read_task_artifact,
    write_task_artifacts,
)
from webscoper.api.resume import (
    resume_langgraph_after_approval as resume_langgraph_after_approval_for_service,
    run_langgraph_workflow,
)
from webscoper.api.runner_factory import build_api_task, build_handler
from webscoper.api.schemas import (
    ApprovalDecisionResponse,
    TaskArtifactContentResponse,
    TaskArtifactListResponse,
    TaskCreateRequest,
    TaskCreateResponse,
    TaskStatusResponse,
)
from webscoper.api.task_state import (
    TaskState as _TaskState,
    status_from_context_state,
    status_from_transcript,
)
from webscoper.runtime.safety.approvals import ApprovalStore
from webscoper.runtime.events import (
    InMemoryTaskEventBus,
    TaskEventStore,
    TaskEventSubscription,
)
from webscoper.runtime.safety.pending import PendingApprovalManager
from webscoper.schemas.events import TaskEvent, TaskEventKind
from webscoper.schemas.risk import ApprovalRequest
from webscoper.schemas.task import TaskSpec
from webscoper.schemas.workflow import LangGraphResumeResult


class TaskService:
    def __init__(self, runs_dir: Path = Path("runs")) -> None:
        self.runs_dir = runs_dir
        self.event_store = TaskEventStore()
        self.event_bus = InMemoryTaskEventBus()
        self.approval_store = ApprovalStore()
        self.pending_manager = PendingApprovalManager()
        self._task_states: dict[str, _TaskState] = {}
        self._langgraph_adapters: dict[str, Any] = {}

    def create_and_run_task(
        self,
        request: TaskCreateRequest,
    ) -> TaskCreateResponse:
        task_id = self._new_task_id()
        run_dir = self._run_dir(task_id)
        run_dir.mkdir(parents=True, exist_ok=True)
        handler = build_handler(self, task_id, request)
        task = build_api_task(task_id, request)

        try:
            self._run_langgraph_workflow(handler, task, task_id)
            context = handler.last_context
            if context is None:
                raise RuntimeError("Task completed without run context.")
            status = status_from_context_state(context.state.status)
            self._write_task_artifacts(context.run_id)
            return TaskCreateResponse(
                task_id=context.run_id,
                status=status,
                run_dir=str(context.run_dir),
                artifacts=list_existing_artifacts(context.run_dir),
                error=context.state.error_message if status != "succeeded" else None,
            )
        except Exception as exc:
            context = handler.last_context
            failed_run_dir = context.run_dir if context is not None else run_dir
            failed_task_id = context.run_id if context is not None else task_id
            status = (
                status_from_context_state(context.state.status)
                if context is not None
                else "failed"
            )
            self._write_task_artifacts(failed_task_id)
            return TaskCreateResponse(
                task_id=failed_task_id,
                status=status if status != "succeeded" else "failed",
                run_dir=str(failed_run_dir),
                artifacts=list_existing_artifacts(failed_run_dir),
                error=str(exc),
            )

    async def create_and_run_task_async(
        self,
        request: TaskCreateRequest,
    ) -> TaskCreateResponse:
        task_id = self._new_task_id()
        run_dir = self._run_dir(task_id)
        run_dir.mkdir(parents=True, exist_ok=True)
        self._task_states[task_id] = _TaskState(
            task_id=task_id,
            status="running",
            run_dir=run_dir,
            workflow=request.workflow,
            thread_id=task_id,
        )
        self._publish_task_event(
            task_id,
            "task_created",
            "Task created",
            {"run_dir": str(run_dir)},
        )
        asyncio.create_task(self._run_async_task(task_id, request))
        return TaskCreateResponse(
            task_id=task_id,
            status="running",
            run_dir=str(run_dir),
            artifacts=[],
            error=None,
        )

    def get_task_status(self, task_id: str) -> TaskStatusResponse:
        if task_id in self._task_states:
            state = self._task_states[task_id]
            state.artifacts = list_existing_artifacts(state.run_dir)
            return TaskStatusResponse(
                task_id=task_id,
                status=state.status,
                run_dir=str(state.run_dir),
                artifacts=state.artifacts,
                error=state.error,
            )

        run_dir = self._run_dir(task_id)
        if not run_dir.exists() or not run_dir.is_dir():
            return TaskStatusResponse(task_id=task_id, status="not_found")

        status, error = status_from_transcript(run_dir)
        return TaskStatusResponse(
            task_id=task_id,
            status=status,
            run_dir=str(run_dir),
            artifacts=list_existing_artifacts(run_dir),
            error=error,
        )

    def list_artifacts(self, task_id: str) -> TaskArtifactListResponse:
        run_dir = self._existing_run_dir(task_id)
        return list_task_artifacts(self, task_id)

    def read_artifact(
        self,
        task_id: str,
        artifact_name: str,
    ) -> TaskArtifactContentResponse:
        return read_task_artifact(self, task_id, artifact_name)

    def get_events(self, task_id: str) -> list[TaskEvent]:
        return self.event_store.list_events(task_id)

    def open_event_subscription(self, task_id: str) -> TaskEventSubscription:
        return self.event_bus.open_subscription(task_id)

    async def subscribe_events(self, task_id: str):
        async for event in self.event_bus.subscribe(task_id):
            yield event

    async def _run_async_task(
        self,
        task_id: str,
        request: TaskCreateRequest,
    ) -> None:
        handler = build_handler(self, task_id, request)
        task = build_api_task(task_id, request)

        state = self._task_states[task_id]
        try:
            await asyncio.to_thread(
                self._run_langgraph_workflow,
                handler,
                task,
                task_id,
            )
            context = handler.last_context
            state.status = (
                status_from_context_state(context.state.status)
                if context is not None
                else "succeeded"
            )
            state.error = (
                context.state.error_message
                if context is not None and state.status != "succeeded"
                else None
            )
        except Exception as exc:
            context = handler.last_context
            state.status = (
                status_from_context_state(context.state.status)
                if context is not None
                else "failed"
            )
            if state.status == "succeeded":
                state.status = "failed"
            state.error = str(exc)
        finally:
            state.artifacts = list_existing_artifacts(state.run_dir)
            write_task_artifacts(self, task_id)

    def _make_event_sink(self, task_id: str):
        def sink(
            kind: TaskEventKind,
            message: str,
            payload: dict[str, Any] | None = None,
        ) -> None:
            self._publish_task_event(task_id, kind, message, payload)

        return sink

    def _publish_task_event(
        self,
        task_id: str,
        kind: TaskEventKind,
        message: str,
        payload: dict[str, Any] | None = None,
    ) -> None:
        try:
            event = self.event_store.append(
                TaskEvent(
                    task_id=task_id,
                    kind=kind,
                    message=message,
                    payload=payload or {},
                )
            )
            self.event_bus.publish(event)
            self.event_store.write_jsonl(task_id, self._run_dir(task_id) / "events.jsonl")
        except Exception:
            return

    def _new_task_id(self) -> str:
        timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S_%f")
        return f"task_{timestamp}"

    def list_approvals(self, task_id: str) -> list[ApprovalRequest]:
        if self.get_task_status(task_id).status == "not_found":
            raise FileNotFoundError(f"Task not found: {task_id}")
        return self.approval_store.list_for_task(task_id)

    def get_approval(self, approval_id: str) -> ApprovalRequest:
        approval = self.approval_store.get(approval_id)
        if approval is None:
            raise FileNotFoundError(f"Approval request not found: {approval_id}")
        return approval

    def decide_approval(
        self,
        approval_id: str,
        approved: bool,
        decided_by: str,
        reason: str | None = None,
    ) -> ApprovalDecisionResponse:
        return decide_approval_for_service(
            self,
            approval_id=approval_id,
            approved=approved,
            decided_by=decided_by,
            reason=reason,
        )

    def resume_langgraph_after_approval(
        self,
        approval_id: str,
        decision,
    ) -> LangGraphResumeResult:
        return resume_langgraph_after_approval_for_service(self, approval_id, decision)

    def _set_task_state(
        self,
        task_id: str,
        status: str,
        error: str | None,
    ) -> None:
        state = self._task_states.get(task_id)
        if state is None:
            run_dir = self._run_dir(task_id)
            if not run_dir.exists():
                return
            state = _TaskState(task_id=task_id, status=status, run_dir=run_dir)
            self._task_states[task_id] = state
        state.status = status
        state.error = error
        state.artifacts = list_existing_artifacts(state.run_dir)

    def _write_task_artifacts(self, task_id: str) -> None:
        write_task_artifacts(self, task_id)

    def _run_langgraph_workflow(
        self,
        handler: WebAgentExecutionHandler,
        task: TaskSpec,
        task_id: str,
    ):
        return run_langgraph_workflow(self, handler, task, task_id)

    def _workflow_for_task(self, task_id: str) -> str:
        return "langgraph"

    def _run_dir(self, task_id: str) -> Path:
        return self.runs_dir / task_id

    def _existing_run_dir(self, task_id: str) -> Path:
        run_dir = self._run_dir(task_id)
        if not run_dir.exists() or not run_dir.is_dir():
            raise FileNotFoundError(f"Task not found: {task_id}")
        return run_dir

    def _list_existing_artifacts(self, run_dir: Path) -> list[str]:
        return list_existing_artifacts(run_dir)

    def _status_from_transcript(self, run_dir: Path) -> tuple[str, str | None]:
        return status_from_transcript(run_dir)
