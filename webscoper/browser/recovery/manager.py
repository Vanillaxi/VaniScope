from __future__ import annotations

from typing import Any

from playwright.async_api import Page

from webscoper.browser.recovery.classifier import RecoveryClassifier
from webscoper.browser.recovery.executor import RecoveryExecutor
from webscoper.browser.recovery.planner import RecoveryPlanner
from webscoper.browser.recovery.strategies import (
    ExecuteClickFn,
    ObserveFn,
    RecoveryStrategies,
    ResolveFn,
    VerifyFn,
    default_observe_with_screenshot,
)
from webscoper.runtime.execution.events import TaskEventSink
from webscoper.runtime.artifacts.evidence import EvidenceStore
from webscoper.runtime.artifacts.trace import TraceRecorder
from webscoper.runtime.artifacts.transcript import TranscriptStore
from webscoper.schemas.browser import ActionResult, EffectVerificationResult
from webscoper.schemas.browser import PageObservation
from webscoper.schemas.browser import RecoveryErrorType, RecoveryPlan, RecoveryResult


class RecoveryManager:
    def __init__(self, max_attempts: int = 2) -> None:
        self.max_attempts = max(1, max_attempts)
        self.classifier = RecoveryClassifier()
        self.planner = RecoveryPlanner(max_attempts=self.max_attempts)
        self.strategies = RecoveryStrategies()
        self.executor = RecoveryExecutor(self.strategies)

    def classify_failure(
        self,
        *,
        error: Exception | None = None,
        action_result: Any | None = None,
        verification_result: Any | None = None,
        observation: Any | None = None,
        target_hint: str | None = None,
    ) -> RecoveryErrorType:
        return self.classifier.classify_failure(
            error=error,
            action_result=action_result,
            verification_result=verification_result,
            observation=observation,
            target_hint=target_hint,
        )

    def build_plan(
        self,
        error_type: RecoveryErrorType,
        observation: Any | None = None,
        target_hint: str | None = None,
    ) -> RecoveryPlan:
        return self.planner.build_plan(
            error_type,
            observation=observation,
            target_hint=target_hint,
        )

    async def recover_click_intent(
        self,
        *,
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
        initial_error_type: RecoveryErrorType | None = None,
        initial_observation: PageObservation | None = None,
        action_result: ActionResult | None = None,
        verification_result: EffectVerificationResult | None = None,
    ) -> RecoveryResult:
        error_type = initial_error_type or self.classify_failure(
            action_result=action_result,
            verification_result=verification_result,
            observation=initial_observation,
            target_hint=target_hint,
        )
        plan = self.build_plan(error_type, initial_observation, target_hint)
        return await self.executor.execute_plan(
            plan=plan,
            page=page,
            task_id=task_id,
            target_hint=target_hint,
            expected_content=expected_content,
            observe_fn=observe_fn,
            resolve_fn=resolve_fn,
            execute_click_fn=execute_click_fn,
            verify_fn=verify_fn,
            trace_recorder=trace_recorder,
            event_sink=event_sink,
            evidence_store=evidence_store,
            transcript_store=transcript_store,
            initial_observation=initial_observation,
        )


__all__ = ["RecoveryManager", "default_observe_with_screenshot"]
