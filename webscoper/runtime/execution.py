from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from webscoper.runtime.agents_md import AgentsMdLoader
from webscoper.runtime.approvals import ApprovalStore
from webscoper.runtime.compaction import ContextCompactor, load_jsonl
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
from webscoper.runtime.llm_reviewer import (
    BaseLLMReportReviewer,
    FakeLLMReportReviewer,
    OpenAICompatibleLLMReportReviewer,
)
from webscoper.runtime.llm_router import LLMProviderRouter
from webscoper.runtime.pending import PendingApprovalManager
from webscoper.runtime.plan_validator import PlanValidator
from webscoper.runtime.planner import DeterministicTaskPlanner, normalize_planner_mode
from webscoper.runtime.prompt_builder import DynamicPromptBuilder
from webscoper.runtime.report import FinalReportBuilder
from webscoper.runtime.reviewer import ReportReviewer, build_review_summary_markdown
from webscoper.runtime.revise_loop import ReviewReviseLoop
from webscoper.runtime.revision import ReportReviser, ReviewRevisionPlanner
from webscoper.runtime.reminders import RuntimeReminderStore
from webscoper.runtime.risk_gate import RiskGate
from webscoper.runtime.tool_executor import LocalToolExecutor
from webscoper.runtime.trace import TraceRecorder
from webscoper.runtime.transcript import TranscriptStore
from webscoper.schemas.context import RuntimeState
from webscoper.schemas.evidence import EvidenceItem
from webscoper.schemas.plan import ExecutionLoopResult, ExecutionPlan
from webscoper.schemas.observation import PageObservation
from webscoper.schemas.prompt import PromptBuildResult
from webscoper.schemas.revise import ReviewerMode
from webscoper.schemas.task import TaskSpec
from webscoper.schemas.version import VersionContext
from webscoper.tools.browser_tools import StatefulBrowserToolRuntime
from webscoper.tools.registry import ToolRegistry, create_default_tool_registry


@dataclass
class WebAgentRuntimeComponents:
    browser_runtime: StatefulBrowserToolRuntime
    tool_executor: LocalToolExecutor
    execution_loop: AgentExecutionLoop


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
        context.state.status = "running"
        context.state.current_step = 1
        transcript.append("execution_started", _state_payload(context))
        self._emit_event(
            "task_started",
            "Task started",
            {"run_id": context.run_id, "run_dir": str(context.run_dir)},
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
        return WebAgentRuntimeComponents(
            browser_runtime=browser_runtime,
            tool_executor=tool_executor,
            execution_loop=execution_loop,
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
        context.transcript_store.append(
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

    def validate_plan(self, context: WebAgentContext, plan: ExecutionPlan):
        validation_result = PlanValidator(self.tool_registry).validate(
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
        await runtime.browser_runtime.start()
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
            llm_reviewer=self._build_llm_reviewer(),
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
            llm_reviewer=self._build_llm_reviewer(),
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

    def _build_llm_reviewer(self) -> BaseLLMReportReviewer | None:
        if self.revise_attempts <= 0:
            return None
        if self.reviewer_mode == ReviewerMode.DETERMINISTIC:
            return None
        if self.reviewer_mode == ReviewerMode.FAKE_LLM:
            return FakeLLMReportReviewer()
        if self.reviewer_mode == ReviewerMode.REAL_LLM:
            if self.llm_config_path is not None:
                client = LLMProviderRouter(self.llm_config_path).create_client(
                    provider_id=self.llm_provider,
                    model_override=self.model_override,
                )
            else:
                client = self._build_llm_client()
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


def _status_from_loop_error(error_type: str | None) -> str | None:
    if error_type == "RISK_APPROVAL_REQUIRED":
        return "requires_approval"
    if error_type == "RISK_BLOCKED":
        return "blocked"
    return None


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
    reviewer_mode: ReviewerMode = ReviewerMode.DETERMINISTIC,
    revise_attempts: int = 0,
    llm_reviewer: BaseLLMReportReviewer | None = None,
) -> None:
    evidence_items, report_text = _persist_evidence_and_final_report(
        context,
        observation,
        event_sink,
    )
    _persist_review_artifacts(
        context,
        report_text,
        evidence_items,
        event_sink,
    )
    _persist_compaction_artifacts(context)
    if revise_attempts > 0:
        _persist_revise_loop_artifacts(
            context=context,
            report_text=report_text,
            evidence_items=evidence_items,
            event_sink=event_sink,
            reviewer_mode=reviewer_mode,
            revise_attempts=revise_attempts,
            llm_reviewer=llm_reviewer,
        )


def _persist_evidence_and_final_report(
    context: WebAgentContext,
    observation: PageObservation,
    event_sink: TaskEventSink | None = None,
) -> tuple[list[EvidenceItem], str]:
    evidence_items: list[EvidenceItem] = []
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
    return evidence_items, report_text


def _persist_review_artifacts(
    context: WebAgentContext,
    report_text: str,
    evidence_items: list[EvidenceItem],
    event_sink: TaskEventSink | None = None,
):
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
    return review_result


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
    compact_context = _read_json_object(context.run_dir / "compact_context.json")
    if llm_reviewer is not None:
        context.transcript_store.append(
            "llm_review_started",
            {"reviewer_mode": reviewer_mode.value},
        )
        _emit_report_event(
            event_sink,
            "llm_review_started",
            "LLM review started",
            {"run_id": context.run_id, "reviewer_mode": reviewer_mode.value},
        )

    loop = ReviewReviseLoop(
        deterministic_reviewer=ReportReviewer(),
        revision_planner=ReviewRevisionPlanner(),
        report_reviser=ReportReviser(),
        llm_reviewer=llm_reviewer,
        max_revisions=revise_attempts,
    )
    result = loop.run(
        task_id=context.run_id,
        task_goal=context.task.raw_input,
        report_markdown=report_text,
        evidence_items=evidence_items,
        compact_context=compact_context,
        output_dir=context.run_dir,
    )
    if llm_reviewer is not None:
        context.transcript_store.append(
            "llm_review_finished",
            {
                "reviewer_mode": reviewer_mode.value,
                "passed": result.llm_review.passed if result.llm_review else None,
                "finding_count": len(result.llm_review.findings)
                if result.llm_review
                else 0,
            },
        )
        _emit_report_event(
            event_sink,
            "llm_review_finished",
            "LLM review finished",
            {
                "run_id": context.run_id,
                "reviewer_mode": reviewer_mode.value,
                "passed": result.llm_review.passed if result.llm_review else None,
            },
        )

    context.transcript_store.append(
        "revision_plan_created",
        {
            "revision_plan_path": str(context.run_dir / "revision_plan.json"),
            "action_count": len(result.revision_plan.actions),
        },
    )
    context.transcript_store.append(
        "report_revised",
        {
            "revised_report_path": str(context.run_dir / "revised_report.md"),
            "revised": result.revision_result.revised,
            "applied_action_count": len(result.revision_result.applied_actions),
        },
    )
    context.transcript_store.append(
        "final_review_finished",
        {
            "final_review_path": str(context.run_dir / "final_review.json"),
            "passed": result.passed,
        },
    )
    context.transcript_store.append(
        "revise_loop_finished",
        {
            "revise_loop_path": str(context.run_dir / "revise_loop.json"),
            "artifacts": result.artifacts,
            "passed": result.passed,
        },
    )
    _emit_report_event(
        event_sink,
        "revision_plan_created",
        "Revision plan created",
        {
            "run_id": context.run_id,
            "action_count": len(result.revision_plan.actions),
        },
    )
    _emit_report_event(
        event_sink,
        "report_revised",
        "Report revised",
        {
            "run_id": context.run_id,
            "revised": result.revision_result.revised,
            "applied_action_count": len(result.revision_result.applied_actions),
        },
    )
    _emit_report_event(
        event_sink,
        "final_review_finished",
        "Final review finished",
        {"run_id": context.run_id, "passed": result.passed},
    )
    _emit_report_event(
        event_sink,
        "revise_loop_finished",
        "Revise loop finished",
        {"run_id": context.run_id, "artifacts": result.artifacts},
    )


def _persist_compaction_artifacts(context: WebAgentContext) -> None:
    run_dir = context.run_dir
    compactor = ContextCompactor()
    risk_report = _read_json_object(run_dir / "risk_report.json")
    result = compactor.compact(
        task_id=context.run_id,
        task_goal=context.task.raw_input,
        transcript_events=load_jsonl(context.transcript_store.transcript_path),
        trace_events=load_jsonl(context.trace_recorder.trace_path),
        evidence_items=context.evidence_store.list_items()
        if context.evidence_store is not None
        else [],
        recovery_attempts=load_jsonl(run_dir / "recovery.jsonl"),
        approval_requests=load_jsonl(run_dir / "approvals.jsonl"),
        risk_report=risk_report,
    )
    compactor.write_artifacts(result, run_dir)
    context.transcript_store.append(
        "compaction_written",
        {
            "compact_context_path": str(run_dir / "compact_context.json"),
            "compact_summary_path": str(run_dir / "compact_summary.md"),
            "compacted": result.compacted,
            "before_counts": result.before_counts,
            "after_counts": result.after_counts,
            "warning_count": len(result.warnings),
        },
    )


def _read_json_object(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


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
