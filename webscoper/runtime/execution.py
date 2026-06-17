from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from webscoper.runtime.agents_md import AgentsMdLoader
from webscoper.runtime.browser_runtime import BrowserRuntime
from webscoper.runtime.context import WebAgentContext
from webscoper.runtime.prompt_builder import DynamicPromptBuilder
from webscoper.runtime.reminders import RuntimeReminderStore
from webscoper.runtime.trace import TraceRecorder
from webscoper.runtime.transcript import TranscriptStore
from webscoper.schemas.context import RuntimeState
from webscoper.schemas.observation import PageObservation
from webscoper.schemas.prompt import PromptBuildResult
from webscoper.schemas.task import TaskSpec
from webscoper.schemas.version import VersionContext
from webscoper.tools.registry import ToolRegistry, create_default_tool_registry


class WebAgentExecutionHandler:
    def __init__(
        self,
        output_root: Path = Path("runs"),
        headless: bool = True,
        version: VersionContext | None = None,
        workspace: Path | None = None,
        agents_md_loader: AgentsMdLoader | None = None,
        tool_registry: ToolRegistry | None = None,
        runtime_reminders: RuntimeReminderStore | None = None,
    ) -> None:
        self.output_root = output_root
        self.headless = headless
        self.version = version or VersionContext()
        self.workspace = workspace
        self.agents_md_loader = agents_md_loader or AgentsMdLoader()
        self.tool_registry = tool_registry or create_default_tool_registry()
        self.runtime_reminders = runtime_reminders or RuntimeReminderStore()
        self.last_context: WebAgentContext | None = None
        self.last_prompt_result: PromptBuildResult | None = None

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
            agents_md_instructions = self.agents_md_loader.load(self.workspace)
            transcript.append(
                "agents_md_loaded",
                {
                    "count": len(agents_md_instructions),
                    "paths": [
                        instruction.source_path
                        for instruction in agents_md_instructions
                    ],
                },
            )

            prompt_result = DynamicPromptBuilder(self.tool_registry).build(
                context.snapshot(),
                agents_md_instructions=agents_md_instructions,
                runtime_reminders=self.runtime_reminders.list(),
            )
            self.last_prompt_result = prompt_result
            _persist_prompt_context(context.run_dir, prompt_result)
            transcript.append(
                "prompt_built",
                {
                    "prompt_preview_path": str(context.run_dir / "prompt_preview.md"),
                    "prompt_context_path": str(context.run_dir / "prompt_context.json"),
                    "loaded_agents_md_paths": prompt_result.loaded_agents_md_paths,
                    "core_tool_ids": prompt_result.core_tool_ids,
                    "lazy_tool_ids": prompt_result.lazy_tool_ids,
                },
            )

            context.state.current_step = 3
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

            context.state.current_step = 4
            transcript.append(
                "browser_runtime_completed",
                _observation_summary(observation),
            )

            context.state.status = "completed"
            context.state.current_step = 5
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


def _persist_prompt_context(run_dir: Path, prompt_result: PromptBuildResult) -> None:
    (run_dir / "prompt_preview.md").write_text(
        prompt_result.prompt_text,
        encoding="utf-8",
    )
    (run_dir / "prompt_context.json").write_text(
        json.dumps(prompt_result.model_dump(mode="json"), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def _observation_summary(observation: PageObservation) -> dict[str, Any]:
    return {
        "url": observation.url,
        "title": observation.title,
        "risk_signals_count": len(observation.risk_signals),
        "interactive_elements_count": len(observation.interactive_elements),
        "screenshot_path": observation.screenshot_path,
    }
