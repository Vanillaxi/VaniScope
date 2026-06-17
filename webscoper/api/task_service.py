from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from webscoper.api.schemas import (
    ApprovalDecisionResponse,
    TaskArtifactContentResponse,
    TaskArtifactListResponse,
    TaskCreateRequest,
    TaskCreateResponse,
    TaskStatusResponse,
)
from webscoper.runtime.approvals import ApprovalStore, ApprovalStoreError
from webscoper.runtime.context import WebAgentContext
from webscoper.runtime.evidence import EvidenceStore
from webscoper.runtime.events import (
    InMemoryTaskEventBus,
    TaskEventStore,
    TaskEventSubscription,
)
from webscoper.runtime.execution import (
    WebAgentExecutionHandler,
    _persist_evidence_and_report,
)
from webscoper.runtime.execution_loop import AgentExecutionLoop
from webscoper.runtime.pending import PendingApprovalManager
from webscoper.runtime.reminders import RuntimeReminderStore
from webscoper.runtime.task_runner import build_task_spec, llm_config_path
from webscoper.runtime.tool_executor import LocalToolExecutor
from webscoper.runtime.trace import TraceRecorder
from webscoper.runtime.transcript import TranscriptStore
from webscoper.schemas.context import RuntimeState, WebAgentContextSnapshot
from webscoper.schemas.events import TaskEvent, TaskEventKind
from webscoper.schemas.plan import ExecutionPlan, PlannedStep
from webscoper.schemas.risk import ApprovalRequest, TaskResumeResult
from webscoper.schemas.task import TaskSpec
from webscoper.schemas.tool_call import ToolCall
from webscoper.tools.browser_tools import StatefulBrowserToolRuntime
from webscoper.tools.registry import create_default_tool_registry


ARTIFACT_ALLOWLIST = {
    "events.jsonl",
    "approvals.jsonl",
    "pending.jsonl",
    "risk_report.json",
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
        self.approval_store = ApprovalStore()
        self.pending_manager = PendingApprovalManager()
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
            approval_store=self.approval_store,
            pending_manager=self.pending_manager,
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
            status = _status_from_context_state(context.state.status)
            return TaskCreateResponse(
                task_id=context.run_id,
                status=status,
                run_dir=str(context.run_dir),
                artifacts=self._list_existing_artifacts(context.run_dir),
                error=context.state.error_message if status != "succeeded" else None,
            )
        except Exception as exc:
            context = handler.last_context
            run_dir = context.run_dir if context is not None else self.runs_dir
            task_id = context.run_id if context is not None else "unknown"
            status = (
                _status_from_context_state(context.state.status)
                if context is not None
                else "failed"
            )
            return TaskCreateResponse(
                task_id=task_id,
                status=status if status != "succeeded" else "failed",
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
            approval_store=self.approval_store,
            pending_manager=self.pending_manager,
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
            context = handler.last_context
            state.status = (
                _status_from_context_state(context.state.status)
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
                _status_from_context_state(context.state.status)
                if context is not None
                else "failed"
            )
            if state.status == "succeeded":
                state.status = "failed"
            state.error = str(exc)
        finally:
            state.artifacts = self._list_existing_artifacts(state.run_dir)
            try:
                self.event_store.write_jsonl(task_id, state.run_dir / "events.jsonl")
                self.approval_store.write_jsonl_for_task(
                    task_id,
                    state.run_dir / "approvals.jsonl",
                )
                self.approval_store.write_risk_report(
                    task_id,
                    state.run_dir / "risk_report.json",
                )
                self.pending_manager.write_jsonl(task_id, state.run_dir / "pending.jsonl")
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
        try:
            approval = self.approval_store.decide(
                approval_id,
                approved=approved,
                decided_by=decided_by,
                reason=reason,
            )
        except ApprovalStoreError as exc:
            raise ValueError(str(exc)) from exc

        run_dir = self._run_dir(approval.task_id)
        resume_result: TaskResumeResult | None = None
        try:
            self.approval_store.write_jsonl_for_task(
                approval.task_id,
                run_dir / "approvals.jsonl",
            )
            self.approval_store.write_risk_report(
                approval.task_id,
                run_dir / "risk_report.json",
            )
            self._publish_task_event(
                approval.task_id,
                "approval_decided",
                "Approval decision recorded",
                {"approval_request": approval.model_dump(mode="json")},
            )
        except Exception:
            pass

        if approved:
            resume_result = asyncio.run(self.resume_after_approval(approval_id))
        else:
            pending = self.pending_manager.pop_by_approval_id(approval_id)
            if pending is not None:
                self.pending_manager.write_jsonl(
                    approval.task_id,
                    run_dir / "pending.jsonl",
                )
            self._set_task_state(
                approval.task_id,
                "rejected",
                "Approval rejected; task will not resume.",
            )
            self._publish_task_event(
                approval.task_id,
                "task_rejected",
                "Approval rejected; task will not resume",
                {"approval_request": approval.model_dump(mode="json")},
            )
            resume_result = TaskResumeResult(
                task_id=approval.task_id,
                approval_id=approval_id,
                resumed=False,
                status="rejected",
                message="Approval rejected; task will not resume.",
                error=None,
            )
        return ApprovalDecisionResponse(approval=approval, resume_result=resume_result)

    async def resume_after_approval(self, approval_id: str) -> TaskResumeResult:
        pending = self.pending_manager.pop_by_approval_id(approval_id)
        approval = self.approval_store.get(approval_id)
        if approval is None:
            return TaskResumeResult(
                task_id="unknown",
                approval_id=approval_id,
                resumed=False,
                status="failed",
                message="Approval request not found.",
                error=f"Approval request not found: {approval_id}",
            )
        task_id = approval.task_id
        run_dir = self._run_dir(task_id)
        if pending is None:
            return TaskResumeResult(
                task_id=task_id,
                approval_id=approval_id,
                resumed=False,
                status=self.get_task_status(task_id).status,
                message="No pending tool call found for approval.",
                error=None,
            )

        self._set_task_state(task_id, "resuming", None)
        self._publish_task_event(
            task_id,
            "task_resumed",
            "Task resumed after approval",
            {"approval_id": approval_id, "pending_tool_call": pending.model_dump(mode="json")},
        )

        try:
            context = self._context_from_pending(pending)
            browser_runtime = StatefulBrowserToolRuntime(
                trace_recorder=context.trace_recorder,
            )
            tool_executor = LocalToolExecutor(
                tool_registry=create_default_tool_registry(),
                browser_runtime=browser_runtime,
                approval_store=self.approval_store,
                pending_manager=self.pending_manager,
                event_sink=self._make_event_sink(task_id),
            )
            execution_loop = AgentExecutionLoop(
                tool_executor=tool_executor,
                event_sink=self._make_event_sink(task_id),
                approval_override_id=approval_id,
            )
            await browser_runtime.start()
            try:
                resume_url = _resume_url_from_pending(pending)
                if resume_url is not None:
                    await browser_runtime.open_observe(resume_url)
                context.transcript_store.append(
                    "task_resumed",
                    {
                        "approval_id": approval_id,
                        "pending_tool_call": pending.model_dump(mode="json"),
                    },
                )
                plan = ExecutionPlan(
                    plan_id=f"resume_{pending.pending_id}",
                    task_id=context.task.task_id,
                    steps=[
                        PlannedStep(
                            step_id="resume_step_001",
                            tool_call=ToolCall(
                                call_id=pending.tool_call_id or "resume_call_001",
                                tool_id=pending.tool_name,
                                arguments=pending.arguments,
                                reason=pending.reason,
                            ),
                            reason=pending.reason,
                            expected_outcome="Approved pending tool call completes.",
                        )
                    ],
                )
                loop_result = await execution_loop.run(
                    context,
                    plan,
                    record_plan_built=False,
                )
                if loop_result.status != "success":
                    raise RuntimeError(
                        f"{loop_result.error_type or 'RESUME_FAILED'}: "
                        f"{loop_result.error_message or 'Resume failed.'}"
                    )
                observation = browser_runtime.last_observation
                if observation is None:
                    raise RuntimeError("Resume completed without a final observation.")
                context.state.status = "completed"
                _persist_evidence_and_report(
                    context,
                    observation,
                    self._make_event_sink(task_id),
                )
                context.transcript_store.append(
                    "execution_completed",
                    {
                        "task_id": context.task.task_id,
                        "run_id": context.run_id,
                        "run_dir": str(context.run_dir),
                        "state": context.state.model_dump(mode="json"),
                    },
                )
                self._set_task_state(task_id, "succeeded", None)
                self._write_task_artifacts(task_id)
                self._publish_task_event(
                    task_id,
                    "task_finished",
                    "Task resumed and finished",
                    {"approval_id": approval_id, "status": "succeeded"},
                )
                return TaskResumeResult(
                    task_id=task_id,
                    approval_id=approval_id,
                    resumed=True,
                    status="succeeded",
                    message="Task resumed and finished.",
                    error=None,
                )
            finally:
                await browser_runtime.close()
        except Exception as exc:
            self._set_task_state(task_id, "failed", str(exc))
            self._write_task_artifacts(task_id)
            self._publish_task_event(
                task_id,
                "resume_failed",
                "Task resume failed",
                {"approval_id": approval_id, "error": str(exc)},
            )
            self._publish_task_event(
                task_id,
                "task_failed",
                "Task failed while resuming",
                {"approval_id": approval_id, "error": str(exc)},
            )
            return TaskResumeResult(
                task_id=task_id,
                approval_id=approval_id,
                resumed=False,
                status="failed",
                message="Task resume failed.",
                error=str(exc),
            )

    def _context_from_pending(self, pending) -> WebAgentContext:
        snapshot_payload = pending.metadata.get("context_snapshot")
        snapshot = WebAgentContextSnapshot.model_validate(snapshot_payload)
        task = TaskSpec.model_validate(snapshot.task.model_dump(mode="json"))
        run_dir = Path(snapshot.trace.run_dir)
        run_id = snapshot.trace.run_id
        return WebAgentContext(
            task=task,
            run_id=run_id,
            run_dir=run_dir,
            trace_recorder=TraceRecorder(run_dir=run_dir, run_id=run_id),
            transcript_store=TranscriptStore(run_dir=run_dir, run_id=run_id),
            evidence_store=EvidenceStore(run_dir / "evidence.jsonl"),
            version=snapshot.version,
            state=RuntimeState(status="resuming"),
        )

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
        state.artifacts = self._list_existing_artifacts(state.run_dir)

    def _write_task_artifacts(self, task_id: str) -> None:
        run_dir = self._run_dir(task_id)
        try:
            self.event_store.write_jsonl(task_id, run_dir / "events.jsonl")
            self.approval_store.write_jsonl_for_task(task_id, run_dir / "approvals.jsonl")
            self.approval_store.write_risk_report(task_id, run_dir / "risk_report.json")
            self.pending_manager.write_jsonl(task_id, run_dir / "pending.jsonl")
        except Exception:
            pass

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
                        state_status = state.get("status")
                        if state_status in {
                            "requires_approval",
                            "blocked",
                            "rejected",
                        }:
                            status = state_status
        return status, error


def _status_from_context_state(state: str) -> str:
    if state == "completed":
        return "succeeded"
    if state in {"requires_approval", "resuming", "blocked", "rejected", "failed"}:
        return state
    return "succeeded"


def _resume_url_from_pending(pending) -> str | None:
    page_observation = pending.metadata.get("page_observation")
    if isinstance(page_observation, dict) and page_observation.get("url"):
        return str(page_observation["url"])
    snapshot = pending.metadata.get("context_snapshot")
    if isinstance(snapshot, dict):
        task = snapshot.get("task")
        if isinstance(task, dict) and task.get("target_url"):
            return str(task["target_url"])
    return None
