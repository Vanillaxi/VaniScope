from __future__ import annotations

import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from webscoper.runtime.agents_md import AgentsMdLoader
from webscoper.runtime.context import WebAgentContext
from webscoper.runtime.evidence import EvidenceStore
from webscoper.runtime.events import TaskEventSink
from webscoper.runtime.execution_loop import AgentExecutionLoop
from webscoper.runtime.llm_client import (
    BaseLLMClient,
    FakeLLMClient,
    OpenAICompatibleLLMClient,
)
from webscoper.runtime.llm_config import load_llm_config_from_env
from webscoper.runtime.llm_planner import LLMTaskPlanner
from webscoper.runtime.llm_router import LLMProviderRouter
from webscoper.runtime.plan_validator import PlanValidator
from webscoper.runtime.planner import DeterministicTaskPlanner, normalize_planner_mode
from webscoper.runtime.prompt_builder import DynamicPromptBuilder
from webscoper.runtime.report import FinalReportBuilder
from webscoper.runtime.reviewer import ReportReviewer, build_review_summary_markdown
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
        llm_config_path: Path | None = None,
        llm_provider: str | None = None,
        run_id_override: str | None = None,
        event_sink: TaskEventSink | None = None,
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
        self.llm_config_path = llm_config_path
        self.llm_provider = llm_provider
        self.run_id_override = run_id_override
        self.event_sink = event_sink
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
            event_sink=self.event_sink,
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
            self._emit_event(
                "task_started",
                "Task started",
                {"run_id": context.run_id, "run_dir": str(context.run_dir)},
            )

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
            self._emit_event(
                "prompt_built",
                "Prompt built",
                {
                    "run_id": context.run_id,
                    "prompt_preview_path": str(context.run_dir / "prompt_preview.md"),
                    "prompt_context_path": str(context.run_dir / "prompt_context.json"),
                    "core_tool_ids": prompt_result.core_tool_ids,
                    "lazy_tool_ids": prompt_result.lazy_tool_ids,
                },
            )

            context.state.current_step = 3
            transcript.append(
                "planner_selected",
                {
                    "planner_mode": self.planner_mode,
                    "llm_config_path": str(self.llm_config_path)
                    if self.llm_config_path is not None
                    else None,
                    "llm_provider": self.llm_provider,
                    "model": self.version.model,
                },
            )
            self._emit_event(
                "planner_started",
                "Planner started",
                {
                    "run_id": context.run_id,
                    "planner_mode": self.planner_mode,
                    "model": self.version.model,
                },
            )
            plan = await self._build_plan(context, prompt_result)
            if self.planner_mode == "real_llm":
                transcript.append(
                    "llm_provider_selected",
                    {
                        "llm_config_path": str(self.llm_config_path)
                        if self.llm_config_path is not None
                        else None,
                        "llm_provider": self.llm_provider,
                        "model": self.version.model,
                    },
                )
            transcript.append("plan_built", plan.model_dump(mode="json"))
            self._emit_event(
                "planner_finished",
                "Planner finished",
                {
                    "run_id": context.run_id,
                    "planner_mode": self.planner_mode,
                    "step_count": len(plan.steps),
                },
            )
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
            _persist_evidence_and_report(context, observation, self.event_sink)
            transcript.append(
                "context_snapshot",
                context.snapshot().model_dump(mode="json"),
            )
            transcript.append("execution_completed", _state_payload(context))
            self._emit_event(
                "task_finished",
                "Task finished",
                {
                    "run_id": context.run_id,
                    "status": "succeeded",
                    "run_dir": str(context.run_dir),
                },
            )
            return observation
        except Exception as exc:
            if context.state.status != "failed":
                context.state.status = "failed"
                context.state.error_type = type(exc).__name__
                context.state.error_message = str(exc)
                transcript.append("execution_failed", _state_payload(context))
            self._emit_event(
                "task_failed",
                "Task failed",
                {
                    "run_id": context.run_id,
                    "status": "failed",
                    "error": str(exc),
                    "error_type": type(exc).__name__,
                    "run_dir": str(context.run_dir),
                },
            )
            transcript.append(
                "context_snapshot",
                context.snapshot().model_dump(mode="json"),
            )
            raise
        finally:
            await browser_runtime.close()

    def run_sync(self, task: TaskSpec) -> PageObservation:
        return asyncio.run(self.run(task))

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
            if self.llm_config_path is not None:
                client = LLMProviderRouter(self.llm_config_path).create_client(
                    provider_id=self.llm_provider,
                    model_override=self.model_override,
                )
                if isinstance(client, OpenAICompatibleLLMClient):
                    self.version.model = client.config.model
                return client
            config = load_llm_config_from_env(self.model_override)
            self.version.model = config.model
            return OpenAICompatibleLLMClient(config)
        raise ValueError(f"Unsupported planner mode: {self.planner_mode}")

    def build_context(self, task: TaskSpec) -> WebAgentContext:
        run_id = self.run_id_override or f"task_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        run_dir = self.output_root / run_id
        trace_recorder = TraceRecorder(run_dir=run_dir, run_id=run_id)
        transcript_store = TranscriptStore(run_dir=run_dir, run_id=run_id)
        return WebAgentContext(
            task=task,
            run_id=run_id,
            run_dir=run_dir,
            trace_recorder=trace_recorder,
            transcript_store=transcript_store,
            evidence_store=EvidenceStore(run_dir / "evidence.jsonl"),
            version=self.version,
            state=RuntimeState(status="context_built"),
        )

    def _emit_event(
        self,
        kind: str,
        message: str,
        payload: dict[str, Any] | None = None,
    ) -> None:
        if self.event_sink is None:
            return
        try:
            self.event_sink(kind, message, payload or {})
        except Exception:
            return


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


def _persist_evidence_and_report(
    context: WebAgentContext,
    observation: PageObservation,
    event_sink: TaskEventSink | None = None,
) -> None:
    evidence_items = []
    if context.evidence_store is not None:
        context.evidence_store.write_jsonl()
        evidence_items = context.evidence_store.list_items()
        context.transcript_store.append(
            "evidence_written",
            {
                "evidence_path": str(context.run_dir / "evidence.jsonl"),
                "evidence_count": len(evidence_items),
            },
        )

    report_path = context.run_dir / "final_report.md"
    report_text = FinalReportBuilder().build_markdown(
        context.task,
        evidence_items,
        final_observation=observation,
    )
    report_path.write_text(report_text, encoding="utf-8")
    context.transcript_store.append(
        "final_report_built",
        {
            "final_report_path": str(report_path),
            "evidence_count": len(evidence_items),
        },
    )
    _emit_report_event(
        event_sink,
        "report_written",
        "Report written",
        {
            "run_id": context.run_id,
            "report_path": str(report_path),
            "evidence_count": len(evidence_items),
        },
    )
    review_result = ReportReviewer().review(
        report_text,
        evidence_items,
        task_spec=context.task,
    )
    review_path = context.run_dir / "review.json"
    review_path.write_text(
        json.dumps(
            review_result.model_dump(mode="json"),
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    review_summary_path = context.run_dir / "review_summary.md"
    review_summary_path.write_text(
        build_review_summary_markdown(review_result),
        encoding="utf-8",
    )
    context.transcript_store.append(
        "review_completed",
        {
            "review_path": str(review_path),
            "review_summary_path": str(review_summary_path),
            "passed": review_result.passed,
            "score": review_result.score,
            "issue_count": len(review_result.issues),
        },
    )
    _emit_report_event(
        event_sink,
        "review_finished",
        "Review finished",
        {
            "run_id": context.run_id,
            "review_path": str(review_path),
            "review_summary_path": str(review_summary_path),
            "passed": review_result.passed,
            "score": review_result.score,
            "issue_count": len(review_result.issues),
        },
    )


def _emit_report_event(
    event_sink: TaskEventSink | None,
    kind: str,
    message: str,
    payload: dict[str, Any],
) -> None:
    if event_sink is None:
        return
    try:
        event_sink(kind, message, payload)
    except Exception:
        return


def _observation_summary(observation: PageObservation) -> dict[str, Any]:
    return {
        "url": observation.url,
        "title": observation.title,
        "risk_signals_count": len(observation.risk_signals),
        "interactive_elements_count": len(observation.interactive_elements),
        "screenshot_path": observation.screenshot_path,
    }
