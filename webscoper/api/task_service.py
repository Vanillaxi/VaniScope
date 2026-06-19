from __future__ import annotations

import asyncio
import json
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
from webscoper.runtime.execution.handler import WebAgentExecutionHandler
from webscoper.runtime.safety.approvals import ApprovalStore
from webscoper.runtime.execution.events import (
    InMemoryTaskEventBus,
    TaskEventStore,
    TaskEventSubscription,
)
from webscoper.runtime.safety.pending import PendingApprovalManager
from webscoper.schemas.runtime import TaskEvent, TaskEventKind
from webscoper.schemas.runtime import ApprovalRequest
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
                skill_id=context.task.skill_id,
                task_type=context.task.task_type,
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
                skill_id=context.task.skill_id if context is not None else request.skill_id,
                task_type=context.task.task_type
                if context is not None
                else (request.task_type or "browser_task"),
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
            skill_id=request.skill_id,
            task_type=request.task_type or "browser_task",
            error=None,
        )

    def get_task_status(self, task_id: str) -> TaskStatusResponse:
        if task_id in self._task_states:
            state = self._task_states[task_id]
            state.artifacts = list_existing_artifacts(state.run_dir)
            metadata = self._task_event_metadata(task_id, state.run_dir)
            skill_metadata = _skill_metadata(state.run_dir)
            return TaskStatusResponse(
                task_id=task_id,
                status=state.status,
                run_dir=str(state.run_dir),
                artifacts=state.artifacts,
                error=state.error,
                created_at=metadata.get("created_at") or state.created_at,
                updated_at=metadata.get("updated_at") or state.updated_at,
                current_step=metadata.get("current_step") or state.current_step,
                current_phase=metadata.get("current_phase") or state.current_phase,
                skill_id=skill_metadata.get("skill_id"),
                task_type=skill_metadata.get("task_type"),
                skill_status=skill_metadata.get("skill_status"),
            )

        run_dir = self._run_dir(task_id)
        if not run_dir.exists() or not run_dir.is_dir():
            return TaskStatusResponse(task_id=task_id, status="not_found")

        status, error = status_from_transcript(run_dir)
        metadata = self._task_event_metadata(task_id, run_dir)
        skill_metadata = _skill_metadata(run_dir)
        return TaskStatusResponse(
            task_id=task_id,
            status=status,
            run_dir=str(run_dir),
            artifacts=list_existing_artifacts(run_dir),
            error=error,
            created_at=metadata.get("created_at"),
            updated_at=metadata.get("updated_at"),
            current_step=metadata.get("current_step"),
            current_phase=metadata.get("current_phase"),
            skill_id=skill_metadata.get("skill_id"),
            task_type=skill_metadata.get("task_type"),
            skill_status=skill_metadata.get("skill_status"),
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
            state = self._task_states.get(task_id)
            if state is not None:
                state.updated_at = event.created_at
                state.current_phase = _event_phase(event)
                step = _event_step(event)
                if step is not None:
                    state.current_step = step
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
        state.updated_at = datetime.now(UTC).isoformat()
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

    def _task_event_metadata(self, task_id: str, run_dir: Path) -> dict[str, Any]:
        events = self.event_store.list_events(task_id)
        if not events:
            events_path = run_dir / "events.jsonl"
            if events_path.exists():
                events = _load_events_from_jsonl(events_path)

        metadata: dict[str, Any] = {}
        if not events:
            return metadata

        metadata["created_at"] = events[0].created_at or None
        metadata["updated_at"] = events[-1].created_at or None
        metadata["current_phase"] = _event_phase(events[-1])
        for event in reversed(events):
            step = _event_step(event)
            if step is not None:
                metadata["current_step"] = step
                break
        return metadata

    def _list_existing_artifacts(self, run_dir: Path) -> list[str]:
        return list_existing_artifacts(run_dir)

    def _status_from_transcript(self, run_dir: Path) -> tuple[str, str | None]:
        return status_from_transcript(run_dir)


def _load_events_from_jsonl(path: Path) -> list[TaskEvent]:
    events: list[TaskEvent] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            events.append(TaskEvent.model_validate_json(line))
        except Exception:
            continue
    return events


def _skill_metadata(run_dir: Path) -> dict[str, str | None]:
    result_path = run_dir / "skill_result.json"
    if result_path.exists():
        try:
            result = json.loads(result_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            result = {}
        if isinstance(result, dict):
            return {
                "skill_id": result.get("skill_id")
                if isinstance(result.get("skill_id"), str)
                else None,
                "task_type": _workflow_task_type(run_dir),
                "skill_status": result.get("status")
                if isinstance(result.get("status"), str)
                else None,
            }

    workflow_path = run_dir / "workflow_state.json"
    if not workflow_path.exists():
        return {"skill_id": None, "task_type": None, "skill_status": None}
    try:
        workflow_state = json.loads(workflow_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"skill_id": None, "task_type": None, "skill_status": None}
    if not isinstance(workflow_state, dict):
        return {"skill_id": None, "task_type": None, "skill_status": None}
    skill_id = workflow_state.get("skill_id")
    task_type = workflow_state.get("task_type")
    return {
        "skill_id": skill_id if isinstance(skill_id, str) else None,
        "task_type": task_type if isinstance(task_type, str) else None,
        "skill_status": None,
    }


def _workflow_task_type(run_dir: Path) -> str | None:
    workflow_path = run_dir / "workflow_state.json"
    if not workflow_path.exists():
        return None
    try:
        workflow_state = json.loads(workflow_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    task_type = workflow_state.get("task_type") if isinstance(workflow_state, dict) else None
    return task_type if isinstance(task_type, str) else None


def _event_phase(event: TaskEvent) -> str:
    phase = event.payload.get("phase")
    if isinstance(phase, str) and phase:
        return phase
    return event.kind


def _event_step(event: TaskEvent) -> int | None:
    for key in ("current_step", "step", "step_index"):
        value = event.payload.get(key)
        if isinstance(value, int):
            return value
        if isinstance(value, str) and value.isdigit():
            return int(value)
    return None
