from __future__ import annotations

import json
from pathlib import Path

from webscoper.api.schemas import (
    TaskArtifactContentResponse,
    TaskArtifactListResponse,
    TaskCreateRequest,
    TaskCreateResponse,
    TaskStatusResponse,
)
from webscoper.runtime.execution import WebAgentExecutionHandler
from webscoper.runtime.reminders import RuntimeReminderStore
from webscoper.runtime.task_runner import build_task_spec, llm_config_path


ARTIFACT_ALLOWLIST = {
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


class TaskService:
    def __init__(self, runs_dir: Path = Path("runs")) -> None:
        self.runs_dir = runs_dir

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

    def get_task_status(self, task_id: str) -> TaskStatusResponse:
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
