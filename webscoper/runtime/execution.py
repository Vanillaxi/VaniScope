from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from webscoper.runtime.browser_runtime import BrowserRuntime
from webscoper.runtime.context import WebAgentContext
from webscoper.runtime.trace import TraceRecorder
from webscoper.runtime.transcript import TranscriptStore
from webscoper.schemas.context import RuntimeState
from webscoper.schemas.observation import PageObservation
from webscoper.schemas.task import TaskSpec
from webscoper.schemas.version import VersionContext


class WebAgentExecutionHandler:
    def __init__(
        self,
        output_root: Path = Path("runs"),
        headless: bool = True,
        version: VersionContext | None = None,
    ) -> None:
        self.output_root = output_root
        self.headless = headless
        self.version = version or VersionContext()
        self.last_context: WebAgentContext | None = None

    async def run(self, task: TaskSpec) -> PageObservation:
        context = self.build_context(task)
        self.last_context = context
        transcript = context.transcript_store
        runtime = BrowserRuntime(
            trace_recorder=context.trace_recorder,
            headless=self.headless,
        )

        transcript.append("task_loaded", _task_payload(task))
        transcript.append(
            "context_built",
            context.snapshot().model_dump(mode="json"),
        )

        try:
            context.state.status = "running"
            context.state.current_step = 1
            transcript.append("execution_started", _state_payload(context))

            context.state.current_step = 2
            transcript.append(
                "browser_runtime_started",
                {
                    "target_url": task.target_url,
                    "has_action": task.action is not None,
                },
            )

            if task.action is None:
                observation = await runtime.open_and_observe(task.target_url)
            else:
                observation = await runtime.open_click_and_observe(
                    task.target_url,
                    task.action,
                )

            context.state.current_step = 3
            transcript.append(
                "browser_runtime_completed",
                _observation_summary(observation),
            )

            context.state.status = "completed"
            context.state.current_step = 4
            transcript.append(
                "context_snapshot",
                context.snapshot().model_dump(mode="json"),
            )
            transcript.append("execution_completed", _state_payload(context))
            return observation
        except Exception as exc:
            context.state.status = "failed"
            context.state.error_type = type(exc).__name__
            context.state.error_message = str(exc)
            transcript.append("execution_failed", _state_payload(context))
            transcript.append(
                "context_snapshot",
                context.snapshot().model_dump(mode="json"),
            )
            raise

    def build_context(self, task: TaskSpec) -> WebAgentContext:
        run_id = f"task_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        run_dir = self.output_root / run_id
        trace_recorder = TraceRecorder(run_dir=run_dir, run_id=run_id)
        transcript_store = TranscriptStore(run_dir=run_dir, run_id=run_id)
        return WebAgentContext(
            task=task,
            run_id=run_id,
            run_dir=run_dir,
            trace_recorder=trace_recorder,
            transcript_store=transcript_store,
            version=self.version,
            state=RuntimeState(status="context_built"),
        )


def _task_payload(task: TaskSpec) -> dict[str, Any]:
    return {
        "task_id": task.task_id,
        "task_type": task.task_type,
        "target_url": task.target_url,
        "has_action": task.action is not None,
        "tags": task.tags,
        "budget": task.budget.model_dump(mode="json"),
        "safety": task.safety.model_dump(mode="json"),
    }


def _state_payload(context: WebAgentContext) -> dict[str, Any]:
    return {
        "task_id": context.task.task_id,
        "run_id": context.run_id,
        "run_dir": str(context.run_dir),
        "state": context.state.model_dump(mode="json"),
    }


def _observation_summary(observation: PageObservation) -> dict[str, Any]:
    return {
        "url": observation.url,
        "title": observation.title,
        "risk_signals_count": len(observation.risk_signals),
        "interactive_elements_count": len(observation.interactive_elements),
        "screenshot_path": observation.screenshot_path,
    }
