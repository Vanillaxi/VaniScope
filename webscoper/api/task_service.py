from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from webscoper.api.schemas import (
    TaskArtifactContentResponse,
    TaskArtifactListResponse,
    TaskCreateRequest,
    TaskCreateResponse,
    TaskStatusResponse,
)
from webscoper.runtime.events import (
    InMemoryTaskEventBus,
    TaskEventStore,
    TaskEventSubscription,
)
from webscoper.runtime.execution import WebAgentExecutionHandler
from webscoper.runtime.reminders import RuntimeReminderStore
from webscoper.runtime.task_runner import build_task_spec, llm_config_path
from webscoper.schemas.events import TaskEvent, TaskEventKind


ARTIFACT_ALLOWLIST = {
    "events.jsonl",
    "trace.jsonl",
    "transcript.jsonl",
    "evidence.jsonl",
    "final_report.md",
    "review.json",
    "review_summary.md",
    "prompt_preview.md",
    "prompt_context.json",
    "score.json",
    "report.md",
}


@dataclass
class _TaskState:
    task_id: str
    status: str
    run_dir: Path
    artifacts: list[str] = field(default_factory=list)
    error: str | None = None


class TaskService:
    def __init__(self, runs_dir: Path = Path("runs")) -> None:
        self.runs_dir = runs_dir
        self.event_store = TaskEventStore()
        self.event_bus = InMemoryTaskEventBus()
        self._task_states: dict[str, _TaskState] = {}

    def create_and_run_task(
        self,
        request: TaskCreateRequest,
    ) -> TaskCreateResponse:
        reminders = RuntimeReminderStore()
        if request.reminder:
            reminders.add(request.reminder, source="api")

        handler = WebAgentExecutionHandler(
            output_root=self.runs_dir,
            workspace=Path(request.workspace) if request.workspace else None,
            runtime_reminders=reminders,
            planner_mode=request.planner,
            model_override=request.model,
            repair_attempts=request.repair_attempts,
            llm_config_path=llm_config_path(request.planner, request.llm_config),
            llm_provider=request.llm_provider,
        )
        task = build_task_spec(
            url=request.url,
            click=request.click,
            expect=request.expect,
            task_id="api_task",
        )

        try:
            handler.run_sync(task)
            context = handler.last_context
            if context is None:
                raise RuntimeError("Task completed without run context.")
            return TaskCreateResponse(
                task_id=context.run_id,
                status="succeeded",
                run_dir=str(context.run_dir),
                artifacts=self._list_existing_artifacts(context.run_dir),
            )
        except Exception as exc:
            context = handler.last_context
            run_dir = context.run_dir if context is not None else self.runs_dir
            task_id = context.run_id if context is not None else "unknown"
            return TaskCreateResponse(
                task_id=task_id,
                status="failed",
                run_dir=str(run_dir),
                artifacts=self._list_existing_artifacts(run_dir),
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
            state.artifacts = self._list_existing_artifacts(state.run_dir)
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

        status, error = self._status_from_transcript(run_dir)
        return TaskStatusResponse(
            task_id=task_id,
            status=status,
            run_dir=str(run_dir),
            artifacts=self._list_existing_artifacts(run_dir),
            error=error,
        )

    def list_artifacts(self, task_id: str) -> TaskArtifactListResponse:
        run_dir = self._existing_run_dir(task_id)
        return TaskArtifactListResponse(
            task_id=task_id,
            artifacts=self._list_existing_artifacts(run_dir),
        )

    def read_artifact(
        self,
        task_id: str,
        artifact_name: str,
    ) -> TaskArtifactContentResponse:
        if artifact_name not in ARTIFACT_ALLOWLIST:
            raise ValueError(f"Artifact is not allowed: {artifact_name}")
        run_dir = self._existing_run_dir(task_id)
        artifact_path = (run_dir / artifact_name).resolve()
        if artifact_path.parent != run_dir.resolve():
            raise ValueError("Artifact path escapes task run directory.")
        if not artifact_path.exists() or not artifact_path.is_file():
            raise FileNotFoundError(f"Artifact not found: {artifact_name}")
        return TaskArtifactContentResponse(
            task_id=task_id,
            artifact_name=artifact_name,
            content=artifact_path.read_text(encoding="utf-8"),
        )

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
        reminders = RuntimeReminderStore()
        if request.reminder:
            reminders.add(request.reminder, source="api")

        handler = WebAgentExecutionHandler(
            output_root=self.runs_dir,
            workspace=Path(request.workspace) if request.workspace else None,
            runtime_reminders=reminders,
            planner_mode=request.planner,
            model_override=request.model,
            repair_attempts=request.repair_attempts,
            llm_config_path=llm_config_path(request.planner, request.llm_config),
            llm_provider=request.llm_provider,
            run_id_override=task_id,
            event_sink=self._make_event_sink(task_id),
        )
        task = build_task_spec(
            url=request.url,
            click=request.click,
            expect=request.expect,
            task_id=task_id,
        )

        state = self._task_states[task_id]
        try:
            await handler.run(task)
            state.status = "succeeded"
            state.error = None
        except Exception as exc:
            state.status = "failed"
            state.error = str(exc)
        finally:
            state.artifacts = self._list_existing_artifacts(state.run_dir)
            try:
                self.event_store.write_jsonl(task_id, state.run_dir / "events.jsonl")
            except Exception:
                pass

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

    def _run_dir(self, task_id: str) -> Path:
        return self.runs_dir / task_id

    def _existing_run_dir(self, task_id: str) -> Path:
        run_dir = self._run_dir(task_id)
        if not run_dir.exists() or not run_dir.is_dir():
            raise FileNotFoundError(f"Task not found: {task_id}")
        return run_dir

    def _list_existing_artifacts(self, run_dir: Path) -> list[str]:
        return [
            artifact
            for artifact in sorted(ARTIFACT_ALLOWLIST)
            if (run_dir / artifact).is_file()
        ]

    def _status_from_transcript(self, run_dir: Path) -> tuple[str, str | None]:
        transcript_path = run_dir / "transcript.jsonl"
        if not transcript_path.exists():
            return "failed", "Missing transcript.jsonl"

        status = "failed"
        error: str | None = None
        for line in transcript_path.read_text(encoding="utf-8").splitlines():
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            event_type = event.get("event_type")
            if event_type == "execution_completed":
                status = "succeeded"
                error = None
            elif event_type == "execution_failed":
                status = "failed"
                payload = event.get("payload")
                if isinstance(payload, dict):
                    state = payload.get("state")
                    if isinstance(state, dict):
                        error = state.get("error_message")
        return status, error
