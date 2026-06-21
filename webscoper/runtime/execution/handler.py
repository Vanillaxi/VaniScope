from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from webscoper.runtime.prompt.agents_md import AgentsMdLoader
from webscoper.runtime.safety.approvals import ApprovalStore
from webscoper.runtime.artifacts.pipeline import (
    emit_report_event,
    persist_compaction_artifacts,
    persist_evidence_and_final_report,
    persist_evidence_and_report,
    persist_prompt_context,
    persist_review_artifacts,
    persist_revise_loop_artifacts,
    read_json_object,
)
from webscoper.runtime.execution.context import WebAgentContext
from webscoper.runtime.artifacts.evidence import EvidenceStore
from webscoper.runtime.execution.events import TaskEventSink
from webscoper.runtime.execution.state import (
    observation_summary,
    state_payload,
    status_from_loop_error,
    task_payload,
)
from webscoper.runtime.execution.loop import AgentExecutionLoop
from webscoper.runtime.llm.client import (
    BaseLLMClient,
)
from webscoper.runtime.llm.config import load_llm_router_config
from webscoper.runtime.llm.planner import LLMTaskPlanner
from webscoper.runtime.llm.reviewer import (
    BaseLLMReportReviewer,
    FakeLLMReportReviewer,
    OpenAICompatibleLLMReportReviewer,
)
from webscoper.runtime.llm.router import AuditedBudgetedLLMClient, LLMProviderRouter
from webscoper.runtime.safety.pending import PendingApprovalManager
from webscoper.runtime.execution.plan_validator import PlanValidator
from webscoper.runtime.execution.planner import DeterministicTaskPlanner, normalize_planner_mode
from webscoper.runtime.prompt.builder import DynamicPromptBuilder
from webscoper.runtime.prompt.reminders import RuntimeReminderStore
from webscoper.runtime.safety.risk_gate import RiskGate
from webscoper.runtime.execution.tool_executor import LocalToolExecutor
from webscoper.runtime.artifacts.trace import TraceRecorder
from webscoper.runtime.artifacts.transcript import TranscriptStore
from webscoper.tools.gateway import (
    BrowserToolProvider,
    FakeMCPToolProvider,
    ToolGateway,
    ToolGatewayAuditStore,
    ToolGatewayPolicy,
)
from webscoper.schemas.runtime import RuntimeState
from webscoper.schemas.artifact import EvidenceItem
from webscoper.schemas.tool import ExecutionLoopResult, ExecutionPlan
from webscoper.schemas.browser import PageObservation
from webscoper.schemas.runtime import PromptBuildResult
from webscoper.schemas.review import ReviewerMode
from webscoper.schemas.task import TaskSpec
from webscoper.schemas.runtime import VersionContext
from webscoper.browser.tool_runtime import StatefulBrowserToolRuntime
from webscoper.browser.public_web import PublicWebRuntimeConfig, load_public_web_config
from webscoper.tools.registry import ToolRegistry, create_default_tool_registry


@dataclass
class WebAgentRuntimeComponents:
    browser_runtime: StatefulBrowserToolRuntime
    tool_executor: LocalToolExecutor
    execution_loop: AgentExecutionLoop
    tool_gateway: ToolGateway


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
        risk_gate: RiskGate | None = None,
        approval_store: ApprovalStore | None = None,
        pending_manager: PendingApprovalManager | None = None,
        reviewer_mode: str = "deterministic",
        revise_attempts: int = 0,
        dry_run: bool = False,
        public_web_config: PublicWebRuntimeConfig | None = None,
        public_web_config_path: Path | None = None,
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
        self.risk_gate = risk_gate or RiskGate()
        self.approval_store = approval_store or ApprovalStore()
        self.pending_manager = pending_manager or PendingApprovalManager()
        self.reviewer_mode = ReviewerMode(reviewer_mode)
        self.revise_attempts = max(0, revise_attempts)
        self.dry_run = dry_run
        self.public_web_config = public_web_config or load_public_web_config(
            public_web_config_path
        )
        if self.model_override:
            self.version.model = self.model_override
        self.last_context: WebAgentContext | None = None
        self.last_prompt_result: PromptBuildResult | None = None
        self.last_loop_result: ExecutionLoopResult | None = None

    async def run(self, task: TaskSpec) -> PageObservation:
        context = self.start_run(task)
        runtime = self.build_runtime_components(context)
        try:
            prompt_result = self.build_prompt(context)
            if self.dry_run:
                self.persist_dry_run_result(context, prompt_result)
                context.state.status = "completed"
                context.state.current_step = 3
                self.finalize_success(context)
                return PageObservation(
                    url=context.task.target_url,
                    title="Dry run",
                    visible_text_summary=(
                        "Dry run completed before LLM planning or browser execution."
                    ),
                    interactive_elements=[],
                    risk_signals=[],
                )
            plan = await self.plan_task(context, prompt_result)
            self.validate_plan(context, plan)
            observation = await self.execute_plan(context, plan, runtime)
            if context.state.status in {"requires_approval", "blocked"}:
                self.snapshot_context(context)
                return observation

            context.state.status = "completed"
            context.state.current_step = 5
            self.persist_run_artifacts(context, observation)
            self.finalize_success(context)
            return observation
        except Exception as exc:
            self.finalize_failure(context, exc)
            raise
        finally:
            await runtime.browser_runtime.close()

    def start_run(self, task: TaskSpec) -> WebAgentContext:
        context = self.build_context(task)
        self.last_context = context
        transcript = context.transcript_store
        transcript.append("task_loaded", _task_payload(task))
        transcript.append(
            "context_built",
            context.snapshot().model_dump(mode="json"),
        )
        transcript.append(
            "public_web_config_loaded",
            self.public_web_config.model_dump(mode="json"),
        )
        context.state.status = "running"
        context.state.current_step = 1
        transcript.append("execution_started", _state_payload(context))
        self._emit_event(
            "task_started",
            "Task started",
            {
                "run_id": context.run_id,
                "run_dir": str(context.run_dir),
                "public_web": self.public_web_config.model_dump(mode="json"),
            },
        )
        return context

    def build_runtime_components(
        self,
        context: WebAgentContext,
    ) -> WebAgentRuntimeComponents:
        browser_runtime = StatefulBrowserToolRuntime(
            trace_recorder=context.trace_recorder,
            headless=self.headless,
            transcript_store=context.transcript_store,
            event_sink=self.event_sink,
            evidence_store=context.evidence_store,
            public_web_config=self.public_web_config,
        )
        tool_executor = LocalToolExecutor(
            tool_registry=self.tool_registry,
            browser_runtime=browser_runtime,
            risk_gate=self.risk_gate,
            approval_store=self.approval_store,
            pending_manager=self.pending_manager,
            event_sink=self.event_sink,
        )
        execution_loop = AgentExecutionLoop(
            tool_executor=tool_executor,
            event_sink=self.event_sink,
        )
        tool_gateway = ToolGateway(
            providers=[
                BrowserToolProvider(
                    browser_runtime=browser_runtime,
                    tool_registry=self.tool_registry,
                ),
                FakeMCPToolProvider(),
            ],
            policy=ToolGatewayPolicy(self.risk_gate),
            audit_store=ToolGatewayAuditStore(context.run_dir / "tool_audit.jsonl"),
            approval_store=self.approval_store,
            pending_manager=self.pending_manager,
            event_sink=self.event_sink,
        )
        return WebAgentRuntimeComponents(
            browser_runtime=browser_runtime,
            tool_executor=tool_executor,
            execution_loop=execution_loop,
            tool_gateway=tool_gateway,
        )

    def build_prompt(self, context: WebAgentContext) -> PromptBuildResult:
        context.state.current_step = 2
        agents_md_instructions = self.agents_md_loader.load(self.workspace)
        context.transcript_store.append(
            "agents_md_loaded",
            {
                "count": len(agents_md_instructions),
                "paths": [
                    instruction.source_path for instruction in agents_md_instructions
                ],
            },
        )

        prompt_result = DynamicPromptBuilder(self.tool_registry).build(
            context.snapshot(),
            agents_md_instructions=agents_md_instructions,
            runtime_reminders=self.runtime_reminders.list(),
            skill=context.skill_context,
        )
        self.last_prompt_result = prompt_result
        _persist_prompt_context(context.run_dir, prompt_result)
        context.transcript_store.append(
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
        return prompt_result

    async def plan_task(
        self,
        context: WebAgentContext,
        prompt_result: PromptBuildResult,
    ) -> ExecutionPlan:
        context.state.current_step = 3
        planner_metadata = self._planner_metadata()
        context.transcript_store.append(
            "planner_selected",
            {
                "planner_mode": self.planner_mode,
                "llm_config_path": str(self.llm_config_path)
                if self.llm_config_path is not None
                else None,
                "llm_provider": planner_metadata.get("provider"),
                "provider": planner_metadata.get("provider"),
                "model": planner_metadata.get("model"),
            },
        )
        self._emit_event(
            "planner_started",
            "Planner started",
            {
                "run_id": context.run_id,
                "planner_mode": self.planner_mode,
                "provider": planner_metadata.get("provider"),
                "model": planner_metadata.get("model"),
            },
        )
        try:
            plan = await self._build_plan(context, prompt_result)
        except RuntimeError as exc:
            if "LLM budget exceeded" in str(exc):
                context.transcript_store.append(
                    "budget_exceeded",
                    {"error": str(exc), "planner_mode": self.planner_mode},
                )
                self._emit_event(
                    "budget_exceeded",
                    "LLM budget exceeded",
                    {"run_id": context.run_id, "error": str(exc)},
                )
            raise
        if self.planner_mode == "real_llm":
            context.transcript_store.append(
                "llm_provider_selected",
                {
                    "llm_config_path": str(self.llm_config_path)
                    if self.llm_config_path is not None
                    else None,
                    "llm_provider": self.llm_provider,
                    "model": self.version.model,
                },
            )
        context.transcript_store.append("plan_built", plan.model_dump(mode="json"))
        self._emit_event(
            "planner_finished",
            "Planner finished",
            {
                "run_id": context.run_id,
                "planner_mode": self.planner_mode,
                "step_count": len(plan.steps),
            },
        )
        return plan

    def persist_dry_run_result(
        self,
        context: WebAgentContext,
        prompt_result: PromptBuildResult,
    ) -> None:
        result = {
            "task_id": context.run_id,
            "dry_run": True,
            "planner_mode": self.planner_mode,
            "llm_provider": self.llm_provider,
            "prompt_preview_path": str(context.run_dir / "prompt_preview.md"),
            "prompt_context_path": str(context.run_dir / "prompt_context.json"),
            "estimated_prompt_tokens": max(1, (len(prompt_result.prompt_text) + 3) // 4),
            "skipped": ["llm_call", "browser_execution"],
        }
        (context.run_dir / "dry_run_result.json").write_text(
            json.dumps(result, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        context.transcript_store.append("dry_run_completed", result)
        self._emit_event("dry_run_completed", "Dry run completed", result)

    def validate_plan(
        self,
        context: WebAgentContext,
        plan: ExecutionPlan,
        tool_gateway: ToolGateway | None = None,
    ):
        validation_result = PlanValidator(
            self.tool_registry,
            tool_gateway=tool_gateway,
        ).validate(
            plan,
            context.snapshot(),
        )
        context.transcript_store.append(
            "plan_validation_completed",
            validation_result.model_dump(mode="json"),
        )
        if not validation_result.ok:
            first_issue = validation_result.issues[0]
            context.state.status = "failed"
            context.state.error_type = first_issue.issue_type
            context.state.error_message = first_issue.message
            context.transcript_store.append(
                "plan_validation_failed",
                validation_result.model_dump(mode="json"),
            )
            context.transcript_store.append("execution_failed", _state_payload(context))
            raise RuntimeError(
                f"Plan validation failed: {first_issue.issue_type}: "
                f"{first_issue.message}"
            )
        return validation_result

    async def execute_plan(
        self,
        context: WebAgentContext,
        plan: ExecutionPlan,
        runtime: WebAgentRuntimeComponents,
    ) -> PageObservation:
        context.transcript_store.append("browser_tool_runtime_started", _state_payload(context))
        context.state.current_step = 4
        loop_result = await runtime.execution_loop.run(
            context,
            plan,
            record_plan_built=False,
        )
        self.last_loop_result = loop_result
        if loop_result.status != "success":
            runtime_status = _status_from_loop_error(loop_result.error_type)
            context.state.status = runtime_status or "failed"
            context.state.error_type = loop_result.error_type
            context.state.error_message = loop_result.error_message
            context.transcript_store.append("execution_failed", _state_payload(context))
            if runtime_status == "blocked":
                self._emit_event(
                    "task_failed",
                    "Task stopped by risk gate",
                    {
                        "run_id": context.run_id,
                        "status": runtime_status,
                        "error_type": loop_result.error_type,
                        "error": loop_result.error_message,
                        "run_dir": str(context.run_dir),
                    },
                )
                self._emit_event(
                    "task_blocked",
                    "Task blocked",
                    {
                        "run_id": context.run_id,
                        "status": runtime_status,
                        "error_type": loop_result.error_type,
                        "error": loop_result.error_message,
                        "run_dir": str(context.run_dir),
                    },
                )
            if runtime_status is not None:
                observation = runtime.browser_runtime.last_observation
                if observation is not None:
                    return observation
            raise RuntimeError(
                f"{loop_result.error_type or 'EXECUTION_LOOP_FAILED'}: "
                f"{loop_result.error_message or 'Execution loop failed.'}"
            )

        observation = runtime.browser_runtime.last_observation
        if observation is None:
            context.state.status = "failed"
            context.state.error_type = "FINAL_OBSERVATION_MISSING"
            context.state.error_message = "Execution loop completed without a final observation."
            context.transcript_store.append("execution_failed", _state_payload(context))
            raise RuntimeError(
                "FINAL_OBSERVATION_MISSING: Execution loop completed without a final observation."
            )
        return observation

    def persist_run_artifacts(
        self,
        context: WebAgentContext,
        observation: PageObservation,
    ) -> None:
        _persist_evidence_and_report(
            context,
            observation,
            self.event_sink,
            reviewer_mode=self.reviewer_mode,
            revise_attempts=self.revise_attempts,
            llm_reviewer=self._build_llm_reviewer(context),
        )

    def build_final_report(
        self,
        context: WebAgentContext,
        observation: PageObservation,
    ) -> tuple[list[EvidenceItem], str]:
        return _persist_evidence_and_final_report(
            context,
            observation,
            self.event_sink,
        )

    def review_report(
        self,
        context: WebAgentContext,
        report_text: str,
        evidence_items: list[EvidenceItem],
    ):
        return _persist_review_artifacts(
            context,
            report_text,
            evidence_items,
            self.event_sink,
        )

    def compact_context(self, context: WebAgentContext) -> None:
        _persist_compaction_artifacts(context)

    def maybe_revise_report(
        self,
        context: WebAgentContext,
        report_text: str,
        evidence_items: list[EvidenceItem],
    ) -> None:
        if self.revise_attempts <= 0:
            return
        _persist_revise_loop_artifacts(
            context=context,
            report_text=report_text,
            evidence_items=evidence_items,
            event_sink=self.event_sink,
            reviewer_mode=self.reviewer_mode,
            revise_attempts=self.revise_attempts,
            llm_reviewer=self._build_llm_reviewer(context),
        )

    def snapshot_context(self, context: WebAgentContext) -> None:
        context.transcript_store.append(
            "context_snapshot",
            context.snapshot().model_dump(mode="json"),
        )

    def finalize_success(self, context: WebAgentContext) -> None:
        self.snapshot_context(context)
        context.transcript_store.append("execution_completed", _state_payload(context))
        self._emit_event(
            "task_finished",
            "Task finished",
            {
                "run_id": context.run_id,
                "status": "succeeded",
                "run_dir": str(context.run_dir),
            },
        )
        self._emit_event(
            "task_succeeded",
            "Task succeeded",
            {
                "run_id": context.run_id,
                "status": "succeeded",
                "run_dir": str(context.run_dir),
            },
        )

    def finalize_failure(self, context: WebAgentContext, exc: Exception) -> None:
        if context.state.status != "failed":
            context.state.status = "failed"
            context.state.error_type = type(exc).__name__
            context.state.error_message = str(exc)
            context.transcript_store.append("execution_failed", _state_payload(context))
        self._emit_event(
            "task_failed",
            "Task failed",
            {
                "run_id": context.run_id,
                "status": context.state.status,
                "error": str(exc),
                "error_type": type(exc).__name__,
                "run_dir": str(context.run_dir),
            },
        )
        self.snapshot_context(context)

    def run_sync(self, task: TaskSpec) -> PageObservation:
        return asyncio.run(self.run(task))

    def _build_llm_reviewer(
        self,
        context: WebAgentContext,
    ) -> BaseLLMReportReviewer | None:
        if self.revise_attempts <= 0:
            return None
        if self.reviewer_mode == ReviewerMode.DETERMINISTIC:
            return None
        if self.reviewer_mode == ReviewerMode.FAKE_LLM:
            return FakeLLMReportReviewer()
        if self.reviewer_mode == ReviewerMode.REAL_LLM:
            client = LLMProviderRouter(self.llm_config_path).create_client(
                provider_id=self.llm_provider,
                model_override=self.model_override,
                run_dir=context.run_dir,
                task_id=context.run_id,
                purpose="reviewer",
                budget=context.task.budget,
            )
            return OpenAICompatibleLLMReportReviewer(
                client=client,
                model=self.version.model,
            )
        return None

    async def _build_plan(
        self,
        context: WebAgentContext,
        prompt_result: PromptBuildResult,
    ) -> ExecutionPlan:
        if context.task.mode == "auto_explore":
            return DeterministicTaskPlanner().build_plan(context.task)
        if self.planner_mode == "deterministic":
            return DeterministicTaskPlanner().build_plan(context.task)

        planner = LLMTaskPlanner(
            self._create_llm_client(context, purpose="planner"),
            repair_attempts=self.repair_attempts,
        )
        try:
            return await planner.build_plan(context.snapshot(), prompt_result)
        finally:
            _append_llm_planner_transcript(context, planner)

    def _create_llm_client(
        self,
        context: WebAgentContext,
        purpose: str,
    ) -> BaseLLMClient:
        if self.llm_client is not None:
            return AuditedBudgetedLLMClient(
                self.llm_client,
                provider="mock",
                model=self.model_override or self.version.model or "mock",
                mode=self.planner_mode,
                audit_path=context.run_dir / "llm_calls.jsonl",
                task_id=context.run_id,
                purpose=purpose,
                budget=context.task.budget,
            )
        if self.planner_mode in {"fake_llm", "real_llm"}:
            client = LLMProviderRouter(self.llm_config_path).create_client(
                provider_id=self.llm_provider,
                model_override=self.model_override,
                run_dir=context.run_dir,
                task_id=context.run_id,
                purpose=purpose,
                budget=context.task.budget,
            )
            return client
        raise ValueError(f"Unsupported planner mode: {self.planner_mode}")

    def _planner_metadata(self) -> dict[str, str | None]:
        if self.llm_client is not None:
            return {
                "provider": "mock",
                "model": self.model_override or self.version.model or "mock",
            }
        if self.planner_mode not in {"fake_llm", "real_llm"}:
            return {"provider": None, "model": self.version.model}
        router = load_llm_router_config(self.llm_config_path)
        provider_id = self.llm_provider or router.default_provider
        provider = router.providers.get(provider_id)
        model = self.model_override or (
            provider.model if provider is not None else router.default_model
        )
        self.version.model = model
        return {"provider": provider_id, "model": model}

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
    return task_payload(task)


def _state_payload(context: WebAgentContext) -> dict[str, Any]:
    return state_payload(context)


def _status_from_loop_error(error_type: str | None) -> str | None:
    return status_from_loop_error(error_type)


def _persist_prompt_context(run_dir: Path, prompt_result: PromptBuildResult) -> None:
    persist_prompt_context(run_dir, prompt_result)


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
    reviewer_mode: ReviewerMode = ReviewerMode.DETERMINISTIC,
    revise_attempts: int = 0,
    llm_reviewer: BaseLLMReportReviewer | None = None,
) -> None:
    persist_evidence_and_report(
        context,
        observation,
        event_sink,
        reviewer_mode,
        revise_attempts,
        llm_reviewer,
    )


def _persist_evidence_and_final_report(
    context: WebAgentContext,
    observation: PageObservation,
    event_sink: TaskEventSink | None = None,
) -> tuple[list[EvidenceItem], str]:
    return persist_evidence_and_final_report(context, observation, event_sink)


def _persist_review_artifacts(
    context: WebAgentContext,
    report_text: str,
    evidence_items: list[EvidenceItem],
    event_sink: TaskEventSink | None = None,
):
    return persist_review_artifacts(context, report_text, evidence_items, event_sink)


def _persist_revise_loop_artifacts(
    *,
    context: WebAgentContext,
    report_text: str,
    evidence_items: list[EvidenceItem],
    event_sink: TaskEventSink | None,
    reviewer_mode: ReviewerMode,
    revise_attempts: int,
    llm_reviewer: BaseLLMReportReviewer | None,
) -> None:
    persist_revise_loop_artifacts(
        context=context,
        report_text=report_text,
        evidence_items=evidence_items,
        event_sink=event_sink,
        reviewer_mode=reviewer_mode,
        revise_attempts=revise_attempts,
        llm_reviewer=llm_reviewer,
    )


def _persist_compaction_artifacts(context: WebAgentContext) -> None:
    persist_compaction_artifacts(context)


def _read_json_object(path: Path) -> dict[str, Any] | None:
    return read_json_object(path)


def _emit_report_event(
    event_sink: TaskEventSink | None,
    kind: str,
    message: str,
    payload: dict[str, Any],
) -> None:
    emit_report_event(event_sink, kind, message, payload)


def _observation_summary(observation: PageObservation) -> dict[str, Any]:
    return observation_summary(observation)
