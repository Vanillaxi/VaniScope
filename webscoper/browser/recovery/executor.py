from __future__ import annotations

from playwright.async_api import Page

from webscoper.runtime.events import TaskEventSink
from webscoper.runtime.artifacts.evidence import EvidenceStore
from webscoper.runtime.artifacts.trace import TraceRecorder
from webscoper.runtime.artifacts.transcript import TranscriptStore
from webscoper.browser.recovery.classifier import observation_summary
from webscoper.browser.recovery.strategies import (
    ExecuteClickFn,
    ObserveFn,
    RecoveryStrategies,
    ResolveFn,
    VerifyFn,
    safe_page_url,
)
from webscoper.browser.recovery.telemetry import RecoveryTelemetry
from webscoper.schemas.observation import PageObservation
from webscoper.schemas.recovery import RecoveryAttempt, RecoveryPlan, RecoveryResult


class RecoveryExecutor:
    def __init__(
        self,
        strategies: RecoveryStrategies,
        telemetry: RecoveryTelemetry | None = None,
    ) -> None:
        self.strategies = strategies
        self.telemetry = telemetry

    async def execute_plan(
        self,
        *,
        plan: RecoveryPlan,
        page: Page,
        task_id: str | None,
        target_hint: str,
        expected_content: str | None,
        observe_fn: ObserveFn,
        resolve_fn: ResolveFn,
        execute_click_fn: ExecuteClickFn,
        verify_fn: VerifyFn,
        trace_recorder: TraceRecorder | None = None,
        event_sink: TaskEventSink | None = None,
        evidence_store: EvidenceStore | None = None,
        transcript_store: TranscriptStore | None = None,
        initial_observation: PageObservation | None = None,
    ) -> RecoveryResult:
        telemetry = self.telemetry or RecoveryTelemetry(
            trace_recorder=trace_recorder,
            event_sink=event_sink,
            evidence_store=evidence_store,
            transcript_store=transcript_store,
            task_id=task_id,
        )
        attempts: list[RecoveryAttempt] = []
        telemetry.emit_started(
            error_type=plan.error_type.value,
            target_hint=target_hint,
            strategies=[strategy.value for strategy in plan.strategies],
        )

        for index, strategy in enumerate(plan.strategies[: plan.max_attempts], start=1):
            attempt = RecoveryAttempt(
                task_id=task_id,
                step_index=index,
                error_type=plan.error_type,
                strategy=strategy,
                status="running",
                reason=plan.reason,
                before_url=safe_page_url(page),
                before_observation_summary=observation_summary(initial_observation),
            )
            telemetry.emit_attempt_started(attempt)

            attempt = await self.strategies.run(
                page=page,
                attempt=attempt,
                strategy=strategy,
                target_hint=target_hint,
                expected_content=expected_content,
                observe_fn=observe_fn,
                resolve_fn=resolve_fn,
                execute_click_fn=execute_click_fn,
                verify_fn=verify_fn,
            )
            attempts.append(attempt)
            telemetry.emit_attempt_finished(attempt)

            if attempt.status == "blocked":
                result = RecoveryResult(
                    recovered=False,
                    blocked=True,
                    final_error_type=plan.error_type,
                    attempts=attempts,
                    message=attempt.reason,
                    metadata={"plan": plan.model_dump(mode="json")},
                )
                telemetry.emit_result(result)
                return result

            if attempt.status == "succeeded":
                result = RecoveryResult(
                    recovered=True,
                    blocked=False,
                    final_error_type=None,
                    attempts=attempts,
                    message="Recovery succeeded.",
                    metadata={"plan": plan.model_dump(mode="json")},
                )
                telemetry.add_recovery_evidence(result, attempt)
                telemetry.emit_result(result)
                return result

        result = RecoveryResult(
            recovered=False,
            blocked=False,
            final_error_type=plan.error_type,
            attempts=attempts,
            message="Recovery failed.",
            metadata={"plan": plan.model_dump(mode="json")},
        )
        telemetry.emit_result(result)
        return result
