from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Awaitable, Callable

from playwright.async_api import Page

from webscoper.browser.observer import observe_page
from webscoper.runtime.artifacts.evidence import EvidenceStore
from webscoper.runtime.artifacts.trace import TraceRecorder, TranscriptStore
from webscoper.runtime.execution.events import TaskEventSink
from webscoper.schemas.browser import (
    ActionResult,
    EffectVerificationResult,
    PageObservation,
    RecoveryAttempt,
    RecoveryErrorType,
    RecoveryPlan,
    RecoveryResult,
    RecoveryStrategy,
)
from webscoper.schemas.artifact import TraceStep


ObserveFn = Callable[[], Awaitable[PageObservation] | PageObservation]
ResolveFn = Callable[[], Awaitable[Any] | Any]
ExecuteClickFn = Callable[..., Awaitable[ActionResult] | ActionResult]
VerifyFn = Callable[[], Awaitable[EffectVerificationResult] | EffectVerificationResult]


class RecoveryManager:
    def __init__(self, max_attempts: int = 2) -> None:
        self.max_attempts = max(1, max_attempts)

    def classify_failure(
        self,
        *,
        error: Exception | None = None,
        action_result: Any | None = None,
        verification_result: Any | None = None,
        observation: Any | None = None,
        target_hint: str | None = None,
    ) -> RecoveryErrorType:
        risk_type = _risk_error_type(observation)
        if risk_type is not None:
            return risk_type

        if action_result is not None:
            action_error = _normalize_error(getattr(action_result, "error_type", None))
            action_message = _normalize_error(getattr(action_result, "error_message", None))
            combined = f"{action_error} {action_message}".strip()
            if "target not found" in combined or "target_not_found" in action_error:
                return RecoveryErrorType.TARGET_NOT_FOUND
            if "ambiguous" in combined:
                return RecoveryErrorType.TARGET_AMBIGUOUS
            if "disabled" in combined and "hydration" in combined:
                return RecoveryErrorType.TARGET_DISABLED_PENDING_HYDRATION
            if "disabled" in combined:
                return RecoveryErrorType.TARGET_DISABLED
            if "overlay" in combined or "covered" in combined:
                return RecoveryErrorType.OVERLAY_BLOCKING_ACTION
            if "loading" in combined or "hydrating" in combined or "skeleton" in combined:
                return RecoveryErrorType.PAGE_STILL_LOADING
            if "timeout" in combined:
                return RecoveryErrorType.NAVIGATION_TIMEOUT

        if verification_result is not None:
            if not bool(getattr(verification_result, "satisfied", False)):
                error_type = _normalize_error(getattr(verification_result, "error_type", None))
                message = _normalize_error(getattr(verification_result, "message", None))
                if "action no effect after transition" in error_type:
                    return RecoveryErrorType.ACTION_NO_EFFECT_AFTER_TRANSITION
                if "timeout" in error_type or "timeout" in message:
                    return RecoveryErrorType.CONTENT_STABILITY_TIMEOUT
                if "no url or page text change" in message:
                    return RecoveryErrorType.ACTION_NO_EFFECT
                return RecoveryErrorType.POSTCONDITION_FAILED

        if error is not None:
            message = _normalize_error(str(error))
            if "timeout" in type(error).__name__.lower() or "timeout" in message:
                return RecoveryErrorType.NAVIGATION_TIMEOUT
            if "overlay" in message or "covered" in message:
                return RecoveryErrorType.OVERLAY_BLOCKING_ACTION

        if target_hint and observation is not None:
            summary = _observation_summary(observation) or ""
            if target_hint.lower() not in summary.lower():
                return RecoveryErrorType.TARGET_NOT_FOUND

        return RecoveryErrorType.UNKNOWN

    def build_plan(
        self,
        error_type: RecoveryErrorType,
        observation: Any | None = None,
        target_hint: str | None = None,
    ) -> RecoveryPlan:
        if error_type in {
            RecoveryErrorType.LOGIN_REQUIRED,
            RecoveryErrorType.CAPTCHA_DETECTED,
            RecoveryErrorType.RISKY_ACTION_BLOCKED,
        }:
            strategies = [RecoveryStrategy.ABORT_AS_BLOCKED]
            reason = "Page requires human-only or blocked interaction."
        elif error_type in {
            RecoveryErrorType.TARGET_DISABLED,
            RecoveryErrorType.UNKNOWN,
        }:
            strategies = [RecoveryStrategy.ABORT_AS_FAILED]
            reason = "No simple safe recovery is available."
        else:
            strategies = [
                RecoveryStrategy.WAIT_AND_REOBSERVE,
                RecoveryStrategy.RETRY_SAME_TARGET,
            ]
            reason = "Wait for the page to settle, then retry the same target once."

        return RecoveryPlan(
            error_type=error_type,
            strategies=strategies,
            max_attempts=self.max_attempts,
            reason=reason,
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
        attempts: list[RecoveryAttempt] = []
        _emit(event_sink, "recovery_started", "Recovery started", _plan_payload(plan, target_hint))

        for index, strategy in enumerate(plan.strategies[: plan.max_attempts], start=1):
            attempt = RecoveryAttempt(
                task_id=task_id,
                step_index=index,
                error_type=plan.error_type,
                strategy=strategy,
                status="running",
                reason=plan.reason,
                before_url=_safe_page_url(page),
                before_observation_summary=_observation_summary(initial_observation),
            )
            _emit_attempt(event_sink, "recovery_attempt_started", attempt)

            if strategy == RecoveryStrategy.ABORT_AS_BLOCKED:
                attempt = _finish_attempt(page, attempt, "blocked", plan.reason)
            elif strategy == RecoveryStrategy.ABORT_AS_FAILED:
                attempt = _finish_attempt(page, attempt, "failed", plan.reason)
            elif strategy == RecoveryStrategy.WAIT_AND_REOBSERVE:
                await page.wait_for_timeout(350)
                observation = await _maybe_await(observe_fn())
                attempt = _finish_attempt(
                    page,
                    attempt,
                    "succeeded" if _observation_has_expected(observation, expected_content) else "failed",
                    "Recovered by waiting and re-observing."
                    if _observation_has_expected(observation, expected_content)
                    else "Page state remained insufficient after waiting.",
                    observation,
                )
            else:
                candidate = await _maybe_await(resolve_fn())
                click_result = await _execute_click(execute_click_fn, candidate)
                verify_result = await _maybe_await(verify_fn())
                observation = await _maybe_await(observe_fn())
                succeeded = (
                    getattr(click_result, "status", None) == "success"
                    and bool(getattr(verify_result, "satisfied", False))
                )
                attempt = _finish_attempt(
                    page,
                    attempt,
                    "succeeded" if succeeded else "failed",
                    "Recovered by retrying the same target."
                    if succeeded
                    else "Retry did not satisfy the expected effect.",
                    observation,
                    metadata={
                        "click_status": getattr(click_result, "status", None),
                        "verification_satisfied": getattr(verify_result, "satisfied", None),
                    },
                )

            attempts.append(attempt)
            _write_attempt(trace_recorder, attempt)
            _record_trace(trace_recorder, attempt)
            _emit_attempt(event_sink, "recovery_attempt_finished", attempt)

            if attempt.status == "blocked":
                result = RecoveryResult(
                    recovered=False,
                    blocked=True,
                    final_error_type=plan.error_type,
                    attempts=attempts,
                    message=attempt.reason,
                    metadata={"plan": plan.model_dump(mode="json")},
                )
                _emit_result(event_sink, result)
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
                _add_recovery_evidence(evidence_store, result, attempt)
                _emit_result(event_sink, result)
                return result

        result = RecoveryResult(
            recovered=False,
            blocked=False,
            final_error_type=plan.error_type,
            attempts=attempts,
            message="Recovery failed.",
            metadata={"plan": plan.model_dump(mode="json")},
        )
        _emit_result(event_sink, result)
        return result


async def default_observe_with_screenshot(page: Page, screenshot_path: Path) -> PageObservation:
    return await observe_page(page, screenshot_path=screenshot_path)


async def _execute_click(execute_click_fn: ExecuteClickFn, candidate: Any) -> Any:
    try:
        return await _maybe_await(execute_click_fn(candidate))
    except TypeError:
        return await _maybe_await(execute_click_fn())


async def _maybe_await(value: Any) -> Any:
    if hasattr(value, "__await__"):
        return await value
    return value


def _finish_attempt(
    page: Page,
    attempt: RecoveryAttempt,
    status: str,
    reason: str,
    observation: PageObservation | None = None,
    metadata: dict[str, Any] | None = None,
) -> RecoveryAttempt:
    attempt.status = status  # type: ignore[assignment]
    attempt.reason = reason
    attempt.after_url = _safe_page_url(page)
    attempt.after_observation_summary = _observation_summary(observation)
    if metadata:
        attempt.metadata.update(metadata)
    return attempt


def _risk_error_type(observation: Any | None) -> RecoveryErrorType | None:
    signals = getattr(observation, "risk_signals", []) or []
    if isinstance(observation, dict):
        signals = observation.get("risk_signals", []) or []
    risk_types = {str(_read(signal, "risk_type") or "").lower() for signal in signals}
    if "captcha" in risk_types:
        return RecoveryErrorType.CAPTCHA_DETECTED
    if "login" in risk_types or "password" in risk_types:
        return RecoveryErrorType.LOGIN_REQUIRED
    return None


def _observation_has_expected(
    observation: PageObservation | None,
    expected_content: str | None,
) -> bool:
    if not expected_content or observation is None:
        return False
    return expected_content.lower() in observation.visible_text_summary.lower()


def _observation_summary(observation: Any | None) -> str | None:
    if observation is None:
        return None
    summary = _read(observation, "visible_text_summary")
    if summary is None:
        return None
    text = str(summary)
    return text if len(text) <= 500 else text[:500].rstrip()


def _read(value: Any, key: str) -> Any:
    if isinstance(value, dict):
        return value.get(key)
    return getattr(value, key, None)


def _normalize_error(value: Any) -> str:
    if value is None:
        return ""
    return str(value).replace("_", " ").lower()


def _safe_page_url(page: Page) -> str | None:
    try:
        return page.url
    except Exception:
        return None


def _plan_payload(plan: RecoveryPlan, target_hint: str) -> dict[str, Any]:
    return {
        "error_type": plan.error_type.value,
        "strategies": [strategy.value for strategy in plan.strategies],
        "target_hint": target_hint,
        "reason": plan.reason,
    }


def _emit_attempt(
    event_sink: TaskEventSink | None,
    event_type: str,
    attempt: RecoveryAttempt,
) -> None:
    _emit(
        event_sink,
        event_type,
        "Recovery attempt started" if event_type.endswith("started") else "Recovery attempt finished",
        {"recovery_attempt": attempt.model_dump(mode="json")},
    )


def _emit_result(event_sink: TaskEventSink | None, result: RecoveryResult) -> None:
    event_type = (
        "recovery_blocked"
        if result.blocked
        else "recovery_succeeded"
        if result.recovered
        else "recovery_failed"
    )
    _emit(
        event_sink,
        event_type,
        result.message,
        {"recovery_result": result.model_dump(mode="json")},
    )
    _emit(
        event_sink,
        "recovery_finished",
        "Recovery finished",
        {
            "status": event_type.replace("recovery_", ""),
            "recovery_result": result.model_dump(mode="json"),
        },
    )


def _emit(
    event_sink: TaskEventSink | None,
    event_type: str,
    message: str,
    payload: dict[str, Any],
) -> None:
    if event_sink is None:
        return
    try:
        event_sink(event_type, message, payload)
    except Exception:
        return


def _write_attempt(
    trace_recorder: TraceRecorder | None,
    attempt: RecoveryAttempt,
) -> None:
    if trace_recorder is None:
        return
    path = trace_recorder.run_dir / "recovery.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(attempt.model_dump(mode="json"), ensure_ascii=False) + "\n")


def _record_trace(
    trace_recorder: TraceRecorder | None,
    attempt: RecoveryAttempt,
) -> None:
    if trace_recorder is None:
        return
    trace_recorder.record(
        TraceStep(
            step_id=attempt.attempt_id,
            run_id=trace_recorder.run_id,
            phase="browser_recovery",
            actor="runtime",
            action_type=f"recovery_{attempt.strategy.value}",
            status=attempt.status,
            url_before=attempt.before_url,
            url_after=attempt.after_url,
            observation=attempt.model_dump(mode="json"),
            error_type=attempt.error_type.value,
            error_message=attempt.reason,
        )
    )


def _add_recovery_evidence(
    evidence_store: EvidenceStore | None,
    result: RecoveryResult,
    attempt: RecoveryAttempt,
) -> None:
    if evidence_store is None:
        return
    evidence_store.add_item(
        kind="recovery_note",
        source_url=attempt.after_url,
        text=result.message,
        step_id=attempt.attempt_id,
        tool_name=f"recovery_{attempt.strategy.value}",
        metadata={
            "recovery_result": result.model_dump(mode="json"),
            "recovery_attempt": attempt.model_dump(mode="json"),
        },
    )


__all__ = ["RecoveryManager", "default_observe_with_screenshot"]
