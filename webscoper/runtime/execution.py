from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from webscoper.runtime.agents_md import AgentsMdLoader
from webscoper.runtime.context import WebAgentContext
from webscoper.runtime.execution_loop import AgentExecutionLoop
from webscoper.runtime.llm_client import (
    BaseLLMClient,
    FakeLLMClient,
    OpenAICompatibleLLMClient,
)
from webscoper.runtime.llm_config import load_llm_config_from_env
from webscoper.runtime.llm_planner import LLMTaskPlanner
from webscoper.runtime.plan_validator import PlanValidator
from webscoper.runtime.planner import DeterministicTaskPlanner, normalize_planner_mode
from webscoper.runtime.prompt_builder import DynamicPromptBuilder
from webscoper.runtime.reminders import RuntimeReminderStore
from webscoper.runtime.tool_executor import LocalToolExecutor
from webscoper.runtime.trace import TraceRecorder
from webscoper.runtime.transcript import TranscriptStore
from webscoper.schemas.context import RuntimeState
from webscoper.schemas.plan import ExecutionLoopResult, ExecutionPlan
from webscoper.schemas.observation import PageObservation
from webscoper.schemas.prompt import PromptBuildResult
from webscoper.schemas.task import TaskSpec
from webscoper.schemas.version import VersionContext
from webscoper.tools.browser_tools import StatefulBrowserToolRuntime
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
        planner_mode: str = "deterministic",
        llm_client: BaseLLMClient | None = None,
        model_override: str | None = None,
        repair_attempts: int = 0,
    ) -> None:
        self.output_root = output_root
        self.headless = headless
        self.version = version or VersionContext()
        self.workspace = workspace
        self.agents_md_loader = agents_md_loader or AgentsMdLoader()
        self.tool_registry = tool_registry or create_default_tool_registry()
        self.runtime_reminders = runtime_reminders or RuntimeReminderStore()
        self.planner_mode = normalize_planner_mode(planner_mode)
        self.llm_client = llm_client
        self.model_override = model_override
        self.repair_attempts = max(0, repair_attempts)
        if self.model_override:
            self.version.model = self.model_override
        self.last_context: WebAgentContext | None = None
        self.last_prompt_result: PromptBuildResult | None = None
        self.last_loop_result: ExecutionLoopResult | None = None

    async def run(self, task: TaskSpec) -> PageObservation:
        context = self.build_context(task)
        self.last_context = context
        transcript = context.transcript_store
        browser_runtime = StatefulBrowserToolRuntime(
            trace_recorder=context.trace_recorder,
            headless=self.headless,
        )
        tool_executor = LocalToolExecutor(
            tool_registry=self.tool_registry,
            browser_runtime=browser_runtime,
        )
        execution_loop = AgentExecutionLoop(
            tool_executor=tool_executor,
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
                "planner_selected",
                {
                    "planner_mode": self.planner_mode,
                },
            )
            plan = await self._build_plan(context, prompt_result)
            transcript.append("plan_built", plan.model_dump(mode="json"))
            validation_result = PlanValidator(self.tool_registry).validate(
                plan,
                context.snapshot(),
            )
            transcript.append(
                "plan_validation_completed",
                validation_result.model_dump(mode="json"),
            )
            if not validation_result.ok:
                first_issue = validation_result.issues[0]
                context.state.status = "failed"
                context.state.error_type = first_issue.issue_type
                context.state.error_message = first_issue.message
                transcript.append(
                    "plan_validation_failed",
                    validation_result.model_dump(mode="json"),
                )
                transcript.append("execution_failed", _state_payload(context))
                raise RuntimeError(
                    f"Plan validation failed: {first_issue.issue_type}: "
                    f"{first_issue.message}"
                )

            transcript.append("browser_tool_runtime_started", _state_payload(context))
            await browser_runtime.start()

            context.state.current_step = 4
            loop_result = await execution_loop.run(
                context,
                plan,
                record_plan_built=False,
            )
            self.last_loop_result = loop_result
            if loop_result.status != "success":
                context.state.status = "failed"
                context.state.error_type = loop_result.error_type
                context.state.error_message = loop_result.error_message
                transcript.append("execution_failed", _state_payload(context))
                raise RuntimeError(
                    f"{loop_result.error_type or 'EXECUTION_LOOP_FAILED'}: "
                    f"{loop_result.error_message or 'Execution loop failed.'}"
                )

            observation = browser_runtime.last_observation
            if observation is None:
                context.state.status = "failed"
                context.state.error_type = "FINAL_OBSERVATION_MISSING"
                context.state.error_message = "Execution loop completed without a final observation."
                transcript.append("execution_failed", _state_payload(context))
                raise RuntimeError(
                    "FINAL_OBSERVATION_MISSING: Execution loop completed without a final observation."
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
            if context.state.status != "failed":
                context.state.status = "failed"
                context.state.error_type = type(exc).__name__
                context.state.error_message = str(exc)
                transcript.append("execution_failed", _state_payload(context))
            transcript.append(
                "context_snapshot",
                context.snapshot().model_dump(mode="json"),
            )
            raise
        finally:
            await browser_runtime.close()

    async def _build_plan(
        self,
        context: WebAgentContext,
        prompt_result: PromptBuildResult,
    ) -> ExecutionPlan:
        if self.planner_mode == "deterministic":
            return DeterministicTaskPlanner().build_plan(context.task)

        planner = LLMTaskPlanner(
            self._create_llm_client(),
            repair_attempts=self.repair_attempts,
        )
        try:
            return await planner.build_plan(context.snapshot(), prompt_result)
        finally:
            _append_llm_planner_transcript(context, planner)

    def _create_llm_client(self) -> BaseLLMClient:
        if self.llm_client is not None:
            return self.llm_client
        if self.planner_mode == "fake_llm":
            return FakeLLMClient()
        if self.planner_mode == "real_llm":
            config = load_llm_config_from_env(self.model_override)
            self.version.model = config.model
            return OpenAICompatibleLLMClient(config)
        raise ValueError(f"Unsupported planner mode: {self.planner_mode}")

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


def _append_llm_planner_transcript(
    context: WebAgentContext,
    planner: LLMTaskPlanner,
) -> None:
    transcript = context.transcript_store
    if planner.last_request is not None:
        transcript.append(
            "llm_request",
            planner.last_request.model_dump(mode="json"),
        )
    if planner.last_response is not None:
        transcript.append(
            "llm_response",
            planner.last_response.model_dump(mode="json"),
        )
    if (
        planner.last_parse_result is not None
        and planner.last_parse_result.status == "failed"
    ):
        transcript.append(
            "tool_call_parse_failed",
            planner.last_parse_result.model_dump(mode="json"),
        )
    for request in planner.repair_requests:
        transcript.append(
            "llm_repair_request",
            request.model_dump(mode="json"),
        )
    for response in planner.repair_responses:
        transcript.append(
            "llm_repair_response",
            response.model_dump(mode="json"),
        )


def _observation_summary(observation: PageObservation) -> dict[str, Any]:
    return {
        "url": observation.url,
        "title": observation.title,
        "risk_signals_count": len(observation.risk_signals),
        "interactive_elements_count": len(observation.interactive_elements),
        "screenshot_path": observation.screenshot_path,
    }
