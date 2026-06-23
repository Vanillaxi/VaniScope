from __future__ import annotations

import asyncio
import json
import threading
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
from webscoper.api.runner_factory import (
    build_api_task,
    build_handler,
    validate_request_planner_configuration,
)
from webscoper.api.schemas import (
    ApprovalDecisionResponse,
    ConversationDetailResponse,
    ConversationResponse,
    MessageResponse,
    RuntimeInspectorResponse,
    RuntimeTimelineResponse,
    RuntimeExecutionGraphResponse,
    TaskArtifactContentResponse,
    TaskArtifactListResponse,
    TaskControlResponse,
    TaskCreateRequest,
    TaskCreateResponse,
    TaskStatusResponse,
)
from webscoper.api.task_state import (
    TaskState as _TaskState,
    status_from_context_state,
    status_from_transcript,
)
from webscoper.browser.public_web import PublicWebRuntimeConfig, load_runtime_config
from webscoper.runtime.persistence import SQLitePersistenceStore, resolve_default_db_path
from webscoper.runtime.execution.handler import WebAgentExecutionHandler
from webscoper.runtime.inspector import (
    RunArtifactLoader,
    RuntimeGraphBuilder,
    RuntimeTimelineBuilder,
)
from webscoper.runtime.safety.approvals import ApprovalStore
from webscoper.runtime.control import TaskControlStore
from webscoper.runtime.execution.events import (
    InMemoryTaskEventBus,
    TaskEventStore,
    TaskEventSubscription,
)
from webscoper.runtime.safety.approvals import PendingApprovalManager
from webscoper.schemas.runtime import TaskEvent, TaskEventKind
from webscoper.schemas.runtime import ApprovalRequest
from webscoper.schemas.task import TaskSpec
from webscoper.schemas.workflow import LangGraphResumeResult


class TaskService:
    def __init__(
        self,
        runs_dir: Path = Path("runs"),
        *,
        web_config: PublicWebRuntimeConfig | None = None,
        runtime_config_path: str | Path | None = None,
        runtime_example_config_path: str | Path | None = None,
        persistence_path: str | Path | None = None,
    ) -> None:
        self.runs_dir = runs_dir
        self.web_config = web_config or load_runtime_config(
            example_path=runtime_example_config_path,
            local_path=runtime_config_path,
        )
        self.event_store = TaskEventStore()
        self.event_bus = InMemoryTaskEventBus()
        self.approval_store = ApprovalStore()
        self.pending_manager = PendingApprovalManager()
        self.control_store = TaskControlStore()
        self.persistence = SQLitePersistenceStore(
            persistence_path
            or resolve_default_db_path(
                runtime_config_path=runtime_config_path,
                fallback_runs_dir=runs_dir,
            )
        )
        self._task_states: dict[str, _TaskState] = {}
        self._task_requests: dict[str, TaskCreateRequest] = {}
        self._langgraph_adapters: dict[str, Any] = {}

    def create_conversation(
        self,
        title: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ConversationResponse:
        return _conversation_response(
            self.persistence.create_conversation(title=title, metadata=metadata)
        )

    def list_conversations(self) -> list[ConversationResponse]:
        return [
            _conversation_response(record)
            for record in self.persistence.list_conversations()
        ]

    def get_conversation(self, conversation_id: str) -> ConversationDetailResponse:
        conversation = self.persistence.get_conversation(conversation_id)
        if conversation is None:
            raise FileNotFoundError(f"Conversation not found: {conversation_id}")
        return ConversationDetailResponse(
            **_conversation_response(conversation).model_dump(mode="json"),
            messages=self.list_messages(conversation_id),
        )

    def list_messages(self, conversation_id: str) -> list[MessageResponse]:
        if self.persistence.get_conversation(conversation_id) is None:
            raise FileNotFoundError(f"Conversation not found: {conversation_id}")
        return [
            _message_response(record)
            for record in self.persistence.list_messages(conversation_id)
        ]

    def create_and_run_task(
        self,
        request: TaskCreateRequest,
    ) -> TaskCreateResponse:
        task_id = self._new_task_id()
        run_dir = self._run_dir(task_id)
        run_dir.mkdir(parents=True, exist_ok=True)
        handler = build_handler(self, task_id, request)
        task = build_api_task(task_id, request)
        self._persist_task_started(request, task, task_id, run_dir)
        self._task_requests[task_id] = request

        try:
            self._run_langgraph_workflow(handler, task, task_id)
            context = handler.last_context
            if context is None:
                raise RuntimeError("Task completed without run context.")
            status = status_from_context_state(context.state.status)
            self._write_task_artifacts(context.run_id)
            self._persist_task_finished(request, context.run_id, status, context.run_dir, None)
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
            self._persist_task_finished(
                request,
                failed_task_id,
                status if status != "succeeded" else "failed",
                failed_run_dir,
                str(exc),
                error_type=type(exc).__name__,
            )
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
        validate_request_planner_configuration(request)
        task_id = self._new_task_id()
        run_dir = self._run_dir(task_id)
        run_dir.mkdir(parents=True, exist_ok=True)
        task = build_api_task(task_id, request)
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
        self._persist_task_started(request, task, task_id, run_dir)
        self._task_requests[task_id] = request
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
                difficulty=skill_metadata.get("difficulty"),
                recommendation=skill_metadata.get("recommendation"),
                display_language=skill_metadata.get("display_language"),
                requested_output_language=skill_metadata.get("requested_output_language"),
                report_language=skill_metadata.get("report_language"),
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
            difficulty=skill_metadata.get("difficulty"),
            recommendation=skill_metadata.get("recommendation"),
            display_language=skill_metadata.get("display_language"),
            requested_output_language=skill_metadata.get("requested_output_language"),
            report_language=skill_metadata.get("report_language"),
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

    def get_timeline(self, task_id: str) -> RuntimeTimelineResponse:
        status = self.get_task_status(task_id)
        if status.status == "not_found":
            raise FileNotFoundError(f"Task not found: {task_id}")
        loader = RunArtifactLoader(self.runs_dir, task_id)
        return RuntimeTimelineBuilder(loader, status=status.status).build_timeline_response()

    def get_inspector(self, task_id: str) -> RuntimeInspectorResponse:
        status = self.get_task_status(task_id)
        if status.status == "not_found":
            raise FileNotFoundError(f"Task not found: {task_id}")
        loader = RunArtifactLoader(self.runs_dir, task_id)
        return RuntimeTimelineBuilder(loader, status=status.status).build_inspector_response(
            status=status.status,
        )

    def get_graph(self, task_id: str) -> RuntimeExecutionGraphResponse:
        status = self.get_task_status(task_id)
        if status.status == "not_found":
            raise FileNotFoundError(f"Task not found: {task_id}")
        loader = RunArtifactLoader(self.runs_dir, task_id)
        return RuntimeGraphBuilder(loader, status=status.status).build_graph_response(
            persist=True,
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
            self._persist_task_finished(
                request,
                task_id,
                state.status,
                state.run_dir,
                state.error,
            )

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
        option: str | None = None,
    ) -> ApprovalDecisionResponse:
        return decide_approval_for_service(
            self,
            approval_id=approval_id,
            approved=approved,
            decided_by=decided_by,
            reason=reason,
            option=option,
        )

    def pause_task(self, task_id: str) -> TaskControlResponse:
        self._ensure_task_exists(task_id)
        self.control_store.request(task_id, "pause")
        self.control_store.write_jsonl(task_id, self._run_dir(task_id) / "user_control.jsonl")
        self._set_task_state(task_id, "paused", None)
        self._publish_task_event(
            task_id,
            "user_pause_requested",
            "User requested task pause",
            {"run_id": task_id},
        )
        return self._control_response(task_id, "pause", "Task pause requested.")

    def resume_task(self, task_id: str) -> TaskControlResponse:
        self._ensure_task_exists(task_id)
        self.control_store.request(task_id, "resume")
        self.control_store.write_jsonl(task_id, self._run_dir(task_id) / "user_control.jsonl")
        self._set_task_state(task_id, "running", None)
        self._publish_task_event(
            task_id,
            "user_resume_requested",
            "User requested task resume",
            {"run_id": task_id},
        )
        self._publish_task_event(
            task_id,
            "task_resumed",
            "Task resumed by user",
            {"run_id": task_id},
        )
        request = self._task_requests.get(task_id)
        if request is not None:
            threading.Thread(
                target=lambda: asyncio.run(self._run_async_task(task_id, request)),
                daemon=True,
            ).start()
        return self._control_response(task_id, "resume", "Task resume requested.")

    def cancel_task(self, task_id: str) -> TaskControlResponse:
        self._ensure_task_exists(task_id)
        self.control_store.request(task_id, "cancel")
        self.control_store.write_jsonl(task_id, self._run_dir(task_id) / "user_control.jsonl")
        self._set_task_state(task_id, "cancel_requested", None)
        self._publish_task_event(
            task_id,
            "user_cancel_requested",
            "User requested task cancel",
            {"run_id": task_id},
        )
        return self._control_response(task_id, "cancel", "Task cancellation requested.")

    def stop_and_summarize_task(
        self,
        task_id: str,
        *,
        reason: str = "Task stopped by user.",
        intro: str | None = None,
    ) -> TaskControlResponse:
        self._ensure_task_exists(task_id)
        current_status = self.get_task_status(task_id).status
        self.control_store.request(task_id, "stop_and_summarize")
        self.control_store.write_jsonl(task_id, self._run_dir(task_id) / "user_control.jsonl")
        self._set_task_state(task_id, "stop_requested", None)
        self._publish_task_event(
            task_id,
            "user_stop_requested",
            "User requested stop and summarize",
            {"run_id": task_id, "reason": reason},
        )
        if current_status in {"paused", "waiting_for_approval", "requires_approval", "failed"}:
            self._generate_partial_report_from_artifacts(task_id, intro=intro)
        return self._control_response(
            task_id,
            "stop_and_summarize",
            "Task stop-and-summarize requested.",
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
        self._persist_artifact_metadata(task_id)
        self._persist_approval_metadata(task_id)

    def _run_langgraph_workflow(
        self,
        handler: WebAgentExecutionHandler,
        task: TaskSpec,
        task_id: str,
    ):
        return run_langgraph_workflow(self, handler, task, task_id)

    def _workflow_for_task(self, task_id: str) -> str:
        return "langgraph"

    def _ensure_task_exists(self, task_id: str) -> None:
        if task_id in self._task_states:
            return
        if not self._run_dir(task_id).exists():
            raise FileNotFoundError(f"Task not found: {task_id}")

    def _control_response(
        self,
        task_id: str,
        action: str,
        message: str,
    ) -> TaskControlResponse:
        status = self.get_task_status(task_id)
        return TaskControlResponse(
            task_id=task_id,
            status=status.status,
            requested_action=action,
            message=message,
            artifacts=status.artifacts,
        )

    def _generate_partial_report_from_artifacts(
        self,
        task_id: str,
        *,
        intro: str | None = None,
    ) -> None:
        run_dir = self._run_dir(task_id)
        intro_text = intro or (
            "Task was stopped by user; this report is generated from evidence collected before stopping."
        )
        evidence_lines: list[str] = []
        evidence_path = run_dir / "evidence.jsonl"
        if evidence_path.exists():
            evidence_lines = [
                line
                for line in evidence_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
        self._publish_task_event(
            task_id,
            "partial_report_started",
            "Partial report generation started",
            {"run_id": task_id, "source": "api"},
        )
        if not evidence_lines:
            report_text = "\n".join(
                [
                    "# VaniScope Partial Task Report",
                    "",
                    intro or "Task stopped before enough evidence was collected.",
                    "",
                ]
            )
        else:
            report_lines = [
                "# VaniScope Partial Task Report",
                "",
                intro_text,
                "",
                "## Evidence",
                "",
            ]
            for index, line in enumerate(evidence_lines, start=1):
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    payload = {}
                evidence_id = payload.get("evidence_id") or f"evidence_{index:03d}"
                kind = payload.get("kind") or "evidence"
                text = str(payload.get("text") or payload.get("source_url") or "")
                if len(text) > 180:
                    text = f"{text[:177]}..."
                report_lines.append(f"- [{evidence_id}] {kind}: {text}")
            report_text = "\n".join(report_lines) + "\n"
        (run_dir / "final_report.md").write_text(report_text, encoding="utf-8")
        self.control_store.clear_transient_flags(task_id)
        self._set_task_state(task_id, "succeeded_partial", None)
        self._publish_task_event(
            task_id,
            "partial_report_generated",
            "Partial report generated",
            {"run_id": task_id, "evidence_count": len(evidence_lines)},
        )
        self._write_task_artifacts(task_id)

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

    def _persist_task_started(
        self,
        request: TaskCreateRequest,
        task: TaskSpec,
        task_id: str,
        run_dir: Path,
    ) -> None:
        try:
            conversation_id = request.conversation_id
            if conversation_id and self.persistence.get_conversation(conversation_id) is None:
                conversation_id = self.persistence.create_conversation(
                    title=_conversation_title(request),
                    metadata={"source": "task_create"},
                ).id
            if conversation_id:
                self.persistence.add_message(
                    conversation_id=conversation_id,
                    role="user",
                    content=request.goal or request.research_goal or request.query or task.raw_input,
                    task_id=task_id,
                    metadata={"url": request.url, "mode": request.mode},
                )
            _write_task_metadata(run_dir, task)
            self.persistence.upsert_task(
                task_id=task_id,
                conversation_id=conversation_id,
                status="running",
                task_type=task.task_type,
                skill_id=task.skill_id,
                input_json=_task_input_json(request, task),
                run_dir=str(run_dir),
            )
        except Exception:
            return

    def _persist_task_finished(
        self,
        request: TaskCreateRequest,
        task_id: str,
        status: str,
        run_dir: Path,
        error: str | None,
        error_type: str | None = None,
    ) -> None:
        try:
            task = build_api_task(task_id, request)
            _write_task_metadata(run_dir, task)
            self.persistence.upsert_task(
                task_id=task_id,
                conversation_id=request.conversation_id,
                status=status,
                task_type=task.task_type,
                skill_id=task.skill_id,
                input_json=_task_input_json(request, task),
                run_dir=str(run_dir),
                error=error,
                error_type=error_type,
            )
            self._persist_artifact_metadata(task_id)
            self._persist_approval_metadata(task_id)
            if request.conversation_id and status in {"succeeded", "failed", "blocked", "rejected"}:
                self.persistence.add_message(
                    conversation_id=request.conversation_id,
                    role="assistant",
                    content=_assistant_task_message(status, task_id, error),
                    task_id=task_id,
                    metadata={"status": status, "run_dir": str(run_dir)},
                )
        except Exception:
            return

    def _persist_artifact_metadata(self, task_id: str) -> None:
        run_dir = self._run_dir(task_id)
        if not run_dir.exists():
            return
        for artifact_name in list_existing_artifacts(run_dir):
            path = run_dir / artifact_name
            try:
                size = path.stat().st_size
            except OSError:
                size = None
            try:
                self.persistence.upsert_artifact(
                    task_id=task_id,
                    name=artifact_name,
                    kind=_artifact_kind(artifact_name),
                    path=str(path),
                    size=size,
                )
            except Exception:
                continue

    def _persist_approval_metadata(self, task_id: str) -> None:
        for approval in self.approval_store.list_for_task(task_id):
            try:
                self.persistence.upsert_approval(
                    approval_id=approval.approval_id,
                    task_id=task_id,
                    status=approval.status,
                    risk_level=approval.risk_level,
                    reason=approval.reason,
                    decision=approval.decision.model_dump(mode="json")
                    if approval.decision is not None
                    else None,
                    created_at=approval.created_at,
                    decided_at=approval.decided_at,
                )
            except Exception:
                continue


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
    task_metadata = _task_metadata(run_dir)
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
                "difficulty": result.get("difficulty")
                if isinstance(result.get("difficulty"), str)
                else None,
                "recommendation": result.get("recommendation")
                if isinstance(result.get("recommendation"), str)
                else None,
                "display_language": _metadata_string(result, "display_language")
                or task_metadata.get("display_language"),
                "requested_output_language": _metadata_string(
                    result,
                    "requested_output_language",
                )
                or task_metadata.get("requested_output_language"),
                "report_language": _metadata_string(result, "report_language")
                or task_metadata.get("report_language"),
            }

    workflow_path = run_dir / "workflow_state.json"
    if not workflow_path.exists():
        return _empty_skill_metadata(task_metadata)
    try:
        workflow_state = json.loads(workflow_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return _empty_skill_metadata(task_metadata)
    if not isinstance(workflow_state, dict):
        return _empty_skill_metadata(task_metadata)
    skill_id = workflow_state.get("skill_id")
    task_type = workflow_state.get("task_type")
    return {
        "skill_id": skill_id if isinstance(skill_id, str) else None,
        "task_type": task_type if isinstance(task_type, str) else None,
        "skill_status": None,
        "difficulty": None,
        "recommendation": None,
        "display_language": task_metadata.get("display_language"),
        "requested_output_language": task_metadata.get("requested_output_language"),
        "report_language": task_metadata.get("report_language"),
    }


def _empty_skill_metadata(
    task_metadata: dict[str, str | None] | None = None,
) -> dict[str, str | None]:
    task_metadata = task_metadata or {}
    return {
        "skill_id": None,
        "task_type": None,
        "skill_status": None,
        "difficulty": None,
        "recommendation": None,
        "display_language": task_metadata.get("display_language"),
        "requested_output_language": task_metadata.get("requested_output_language"),
        "report_language": task_metadata.get("report_language"),
    }


def _task_metadata(run_dir: Path) -> dict[str, str | None]:
    path = run_dir / "task_metadata.json"
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    if not isinstance(payload, dict):
        return {}
    return {
        "display_language": payload.get("display_language")
        if isinstance(payload.get("display_language"), str)
        else None,
        "requested_output_language": payload.get("requested_output_language")
        if isinstance(payload.get("requested_output_language"), str)
        else None,
        "report_language": payload.get("report_language")
        if isinstance(payload.get("report_language"), str)
        else None,
    }


def _metadata_string(result: dict[str, Any], key: str) -> str | None:
    metadata = result.get("metadata") if isinstance(result.get("metadata"), dict) else {}
    value = metadata.get(key)
    return value if isinstance(value, str) else None


def _task_input_json(request: TaskCreateRequest, task: TaskSpec) -> dict[str, Any]:
    payload = request.model_dump(mode="json")
    payload.update(
        {
            "display_language": task.display_language,
            "requested_output_language": task.requested_output_language,
            "report_language": task.report_language,
        }
    )
    return payload


def _write_task_metadata(run_dir: Path, task: TaskSpec) -> None:
    try:
        (run_dir / "task_metadata.json").write_text(
            json.dumps(
                {
                    "task_id": task.task_id,
                    "display_language": task.display_language,
                    "requested_output_language": task.requested_output_language,
                    "report_language": task.report_language,
                },
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
    except Exception:
        return


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


def _conversation_response(record) -> ConversationResponse:
    return ConversationResponse(
        id=record.id,
        title=record.title,
        created_at=record.created_at,
        updated_at=record.updated_at,
        last_task_id=record.last_task_id,
        metadata_json=record.metadata_json or {},
    )


def _message_response(record) -> MessageResponse:
    return MessageResponse(
        id=record.id,
        conversation_id=record.conversation_id,
        role=record.role,
        content=record.content,
        task_id=record.task_id,
        metadata_json=record.metadata_json,
        created_at=record.created_at,
    )


def _conversation_title(request: TaskCreateRequest) -> str:
    title = request.goal or request.research_goal or request.query or request.url
    return title[:80]


def _assistant_task_message(status: str, task_id: str, error: str | None) -> str:
    if status == "succeeded":
        return f"Task {task_id} completed successfully."
    return f"Task {task_id} ended with status {status}: {error or 'no error message'}"


def _artifact_kind(name: str) -> str:
    suffix = Path(name).suffix.lower().lstrip(".")
    if name.endswith(".jsonl"):
        return "jsonl"
    if name.endswith(".md"):
        return "markdown"
    return suffix or "artifact"
