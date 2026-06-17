from __future__ import annotations

import inspect
import json
from pathlib import Path
from typing import Any, Awaitable, Callable

from playwright.async_api import Page

from webscoper.browser.observer import observe_page
from webscoper.runtime.events import TaskEventSink
from webscoper.runtime.evidence import EvidenceStore
from webscoper.runtime.trace import TraceRecorder
from webscoper.runtime.transcript import TranscriptStore
from webscoper.schemas.action import ActionResult, EffectVerificationResult
from webscoper.schemas.observation import PageObservation
from webscoper.schemas.recovery import (
    RecoveryAttempt,
    RecoveryErrorType,
    RecoveryPlan,
    RecoveryResult,
    RecoveryStrategy,
)
from webscoper.schemas.trace import TraceStep


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
            action_error = _normalized_error_text(
                getattr(action_result, "error_type", None)
            )
            action_message = _normalized_error_text(
                getattr(action_result, "error_message", None)
            )
            combined = f"{action_error} {action_message}".strip()
            if "target_not_found" in action_error or "target not found" in combined:
                return RecoveryErrorType.TARGET_NOT_FOUND
            if "target_ambiguous" in action_error or "ambiguous" in combined:
                return RecoveryErrorType.TARGET_AMBIGUOUS
            if "target_disabled" in action_error or "disabled" in combined:
                return RecoveryErrorType.TARGET_DISABLED
            if _looks_covered(combined):
                return RecoveryErrorType.TARGET_COVERED
            if "timeout" in combined:
                return RecoveryErrorType.NAVIGATION_TIMEOUT

        if verification_result is not None:
            satisfied = bool(getattr(verification_result, "satisfied", False))
            if not satisfied:
                error_type = _normalized_error_text(
                    getattr(verification_result, "error_type", None)
                )
                message = _normalized_error_text(
                    getattr(verification_result, "message", None)
                )
                if "timeout" in error_type or "timeout" in message:
                    return RecoveryErrorType.NAVIGATION_TIMEOUT
                if "no url or page text change" in message:
                    return RecoveryErrorType.ACTION_NO_EFFECT
                return RecoveryErrorType.POSTCONDITION_FAILED

        if error is not None:
            message = _normalized_error_text(str(error))
            if _looks_covered(message):
                return RecoveryErrorType.TARGET_COVERED
            if "timeout" in type(error).__name__.lower() or "timeout" in message:
                return RecoveryErrorType.NAVIGATION_TIMEOUT

        if target_hint and observation is not None:
            summary = _normalized_error_text(_observation_summary(observation))
            if target_hint.lower() not in summary:
                return RecoveryErrorType.TARGET_NOT_FOUND

        return RecoveryErrorType.UNKNOWN

    def build_plan(
        self,
        error_type: RecoveryErrorType,
        observation: Any | None = None,
        target_hint: str | None = None,
    ) -> RecoveryPlan:
        if error_type == RecoveryErrorType.TARGET_NOT_FOUND:
            strategies = [
                RecoveryStrategy.WAIT_AND_REOBSERVE,
                RecoveryStrategy.SCROLL_AND_REOBSERVE,
                RecoveryStrategy.RETRY_ALTERNATIVE_TARGET,
            ]
            reason = "Target was not found; wait for lazy content, re-observe, then retry."
        elif error_type == RecoveryErrorType.TARGET_AMBIGUOUS:
            strategies = [RecoveryStrategy.RETRY_ALTERNATIVE_TARGET]
            reason = "Target matched multiple candidates; try an alternate candidate if available."
        elif error_type == RecoveryErrorType.TARGET_DISABLED:
            strategies = [RecoveryStrategy.ABORT_AS_FAILED]
            reason = "Disabled targets are not safe to force-click."
        elif error_type == RecoveryErrorType.TARGET_COVERED:
            strategies = [
                RecoveryStrategy.CLOSE_MODAL_IF_SAFE,
                RecoveryStrategy.SCROLL_AND_REOBSERVE,
                RecoveryStrategy.RETRY_SAME_TARGET,
            ]
            reason = "Target appears covered; close safe modal controls before retrying."
        elif error_type in {
            RecoveryErrorType.ACTION_NO_EFFECT,
            RecoveryErrorType.POSTCONDITION_FAILED,
        }:
            strategies = [
                RecoveryStrategy.WAIT_AND_REOBSERVE,
                RecoveryStrategy.RETRY_SAME_TARGET,
                RecoveryStrategy.RETRY_ALTERNATIVE_TARGET,
            ]
            reason = "Action completed but expected effect was not observed."
        elif error_type == RecoveryErrorType.NAVIGATION_TIMEOUT:
            strategies = [
                RecoveryStrategy.WAIT_AND_REOBSERVE,
                RecoveryStrategy.ABORT_AS_FAILED,
            ]
            reason = "Navigation timed out; wait once and inspect current page state."
        elif error_type in {
            RecoveryErrorType.LOGIN_REQUIRED,
            RecoveryErrorType.CAPTCHA_DETECTED,
            RecoveryErrorType.RISKY_ACTION_BLOCKED,
        }:
            strategies = [RecoveryStrategy.ABORT_AS_BLOCKED]
            reason = "Page requires a blocked or human-only action."
        else:
            strategies = [RecoveryStrategy.ABORT_AS_FAILED]
            reason = "No safe recovery strategy matched the failure."

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
        _emit(
            event_sink,
            transcript_store,
            "recovery_started",
            "Recovery started",
            task_id,
            {
                "error_type": error_type.value,
                "target_hint": target_hint,
                "strategies": [strategy.value for strategy in plan.strategies],
            },
        )

        for index, strategy in enumerate(plan.strategies[: plan.max_attempts], start=1):
            before_observation = initial_observation
            before_url = _safe_page_url(page)
            attempt = RecoveryAttempt(
                task_id=task_id,
                step_index=index,
                error_type=error_type,
                strategy=strategy,
                status="running",
                reason=plan.reason,
                before_url=before_url,
                before_observation_summary=_observation_summary(before_observation),
            )
            _record_trace(trace_recorder, attempt, "recovery_attempt", "running")
            _emit(
                event_sink,
                transcript_store,
                "recovery_attempt_started",
                "Recovery attempt started",
                task_id,
                attempt.model_dump(mode="json"),
            )

            attempt = await self._run_strategy(
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
            _write_attempt(trace_recorder, attempt)
            _record_trace(trace_recorder, attempt, "recovery_attempt", attempt.status)
            _emit(
                event_sink,
                transcript_store,
                "recovery_attempt_finished",
                "Recovery attempt finished",
                task_id,
                attempt.model_dump(mode="json"),
            )

            if attempt.status == "blocked":
                result = RecoveryResult(
                    recovered=False,
                    blocked=True,
                    final_error_type=error_type,
                    attempts=attempts,
                    message=attempt.reason,
                    metadata={"plan": plan.model_dump(mode="json")},
                )
                _emit_result(event_sink, transcript_store, task_id, result)
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
                _emit_result(event_sink, transcript_store, task_id, result)
                return result

        result = RecoveryResult(
            recovered=False,
            blocked=False,
            final_error_type=error_type,
            attempts=attempts,
            message="Recovery failed.",
            metadata={"plan": plan.model_dump(mode="json")},
        )
        _emit_result(event_sink, transcript_store, task_id, result)
        return result

    async def _run_strategy(
        self,
        *,
        page: Page,
        attempt: RecoveryAttempt,
        strategy: RecoveryStrategy,
        target_hint: str,
        expected_content: str | None,
        observe_fn: ObserveFn,
        resolve_fn: ResolveFn,
        execute_click_fn: ExecuteClickFn,
        verify_fn: VerifyFn,
    ) -> RecoveryAttempt:
        try:
            if strategy == RecoveryStrategy.ABORT_AS_BLOCKED:
                return _finish_attempt(
                    attempt,
                    page,
                    "blocked",
                    "Recovery blocked by login, captcha, or risk signal.",
                )
            if strategy == RecoveryStrategy.ABORT_AS_FAILED:
                return _finish_attempt(
                    attempt,
                    page,
                    "failed",
                    "Recovery aborted; no safe retry is available.",
                )
            if strategy == RecoveryStrategy.WAIT_AND_REOBSERVE:
                await page.wait_for_timeout(800)
                observation = await _call(observe_fn)
                risk_type = _risk_error_type(observation)
                if risk_type is not None:
                    return _finish_attempt(
                        attempt,
                        page,
                        "blocked",
                        f"Recovery blocked by {risk_type.value}.",
                        observation,
                        {"risk_type": risk_type.value},
                    )
                if _observation_has_expected(observation, expected_content):
                    return _finish_attempt(
                        attempt,
                        page,
                        "succeeded",
                        "Expected content appeared after waiting.",
                        observation,
                    )
                return await _retry_click_and_verify(
                    page=page,
                    attempt=attempt,
                    observe_fn=observe_fn,
                    resolve_fn=resolve_fn,
                    execute_click_fn=execute_click_fn,
                    verify_fn=verify_fn,
                    fallback_reason="Target was still unavailable after waiting.",
                )
            if strategy == RecoveryStrategy.SCROLL_AND_REOBSERVE:
                await page.evaluate("() => window.scrollBy(0, Math.max(300, window.innerHeight / 2))")
                await page.wait_for_timeout(250)
                return await _retry_click_and_verify(
                    page=page,
                    attempt=attempt,
                    observe_fn=observe_fn,
                    resolve_fn=resolve_fn,
                    execute_click_fn=execute_click_fn,
                    verify_fn=verify_fn,
                    fallback_reason="Retry after scroll did not satisfy the expected effect.",
                )
            if strategy == RecoveryStrategy.RETRY_SAME_TARGET:
                return await _retry_click_and_verify(
                    page=page,
                    attempt=attempt,
                    observe_fn=observe_fn,
                    resolve_fn=resolve_fn,
                    execute_click_fn=execute_click_fn,
                    verify_fn=verify_fn,
                    fallback_reason="Retrying the same target did not satisfy the expected effect.",
                )
            if strategy == RecoveryStrategy.RETRY_ALTERNATIVE_TARGET:
                resolved = await _call(resolve_fn)
                candidates = list(getattr(resolved, "candidates", []) or [])
                if len(candidates) < 2:
                    observation = await _call(observe_fn)
                    return _finish_attempt(
                        attempt,
                        page,
                        "failed",
                        "No alternative target candidate was available.",
                        observation,
                        {"candidate_count": len(candidates)},
                    )
                return await _retry_click_and_verify(
                    page=page,
                    attempt=attempt,
                    observe_fn=observe_fn,
                    resolve_fn=resolve_fn,
                    execute_click_fn=execute_click_fn,
                    verify_fn=verify_fn,
                    fallback_reason="Alternative target retry failed.",
                    candidate=candidates[1],
                )
            if strategy == RecoveryStrategy.CLOSE_MODAL_IF_SAFE:
                closed = await _close_safe_modal_control(page)
                observation = await _call(observe_fn)
                if not closed:
                    return _finish_attempt(
                        attempt,
                        page,
                        "failed",
                        "No safe modal close control was found.",
                        observation,
                    )
                return await _retry_click_and_verify(
                    page=page,
                    attempt=attempt,
                    observe_fn=observe_fn,
                    resolve_fn=resolve_fn,
                    execute_click_fn=execute_click_fn,
                    verify_fn=verify_fn,
                    fallback_reason="Target retry after closing modal failed.",
                    metadata={"closed_modal": True},
                )
            if strategy == RecoveryStrategy.OPEN_HREF_DIRECTLY:
                observation = await _call(observe_fn)
                return _finish_attempt(
                    attempt,
                    page,
                    "skipped",
                    "Opening href directly is not enabled in the MVP.",
                    observation,
                )
        except Exception as exc:
            observation = await _safe_observe(observe_fn)
            return _finish_attempt(
                attempt,
                page,
                "failed",
                f"Recovery attempt raised {type(exc).__name__}: {exc}",
                observation,
                {"exception_type": type(exc).__name__},
            )

        observation = await _safe_observe(observe_fn)
        return _finish_attempt(
            attempt,
            page,
            "failed",
            "Recovery strategy was not handled.",
            observation,
        )


async def _retry_click_and_verify(
    *,
    page: Page,
    attempt: RecoveryAttempt,
    observe_fn: ObserveFn,
    resolve_fn: ResolveFn,
    execute_click_fn: ExecuteClickFn,
    verify_fn: VerifyFn,
    fallback_reason: str,
    candidate: Any | None = None,
    metadata: dict[str, Any] | None = None,
) -> RecoveryAttempt:
    resolved = await _call(resolve_fn)
    action_result = await _call_with_optional_arg(execute_click_fn, candidate)
    verification_result = await _call(verify_fn)
    observation = await _call(observe_fn)
    attempt_metadata = {
        "resolved": _dump_model(resolved),
        "action_result": _dump_model(action_result),
        "verification_result": _dump_model(verification_result),
    }
    if metadata:
        attempt_metadata.update(metadata)
    if candidate is not None:
        attempt_metadata["candidate"] = _dump_model(candidate)
    if getattr(action_result, "status", None) == "success" and bool(
        getattr(verification_result, "satisfied", False)
    ):
        return _finish_attempt(
            attempt,
            page,
            "succeeded",
            "Retry satisfied the expected effect.",
            observation,
            attempt_metadata,
        )
    return _finish_attempt(
        attempt,
        page,
        "failed",
        fallback_reason,
        observation,
        attempt_metadata,
    )


async def _close_safe_modal_control(page: Page) -> bool:
    safe_names = ["close", "x", "dismiss", "cancel", "关闭", "取消"]
    risky_names = ["submit", "confirm", "pay", "delete", "publish", "购买", "删除", "确认"]
    for name in safe_names:
        locator = page.get_by_role("button", name=name, exact=False)
        try:
            count = min(await locator.count(), 3)
        except Exception:
            count = 0
        for index in range(count):
            current = locator.nth(index)
            try:
                text = ((await current.inner_text(timeout=500)) or name).strip().lower()
            except Exception:
                text = name.lower()
            if any(risky in text for risky in risky_names):
                continue
            try:
                if await current.is_visible() and await current.is_enabled():
                    await current.click(timeout=1000)
                    await page.wait_for_timeout(250)
                    return True
            except Exception:
                continue
    return False


def _risk_error_type(observation: Any | None) -> RecoveryErrorType | None:
    signals = getattr(observation, "risk_signals", []) or []
    risk_types = {str(getattr(signal, "risk_type", "")).lower() for signal in signals}
    if "captcha" in risk_types:
        return RecoveryErrorType.CAPTCHA_DETECTED
    if "login" in risk_types or "password" in risk_types:
        return RecoveryErrorType.LOGIN_REQUIRED
    return None


def _looks_covered(value: str) -> bool:
    return any(
        needle in value
        for needle in [
            "intercepts pointer events",
            "covered",
            "overlay",
            "modal",
            "not visible",
            "receives pointer events",
        ]
    )


def _normalized_error_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).replace("_", " ").lower()


def _observation_summary(observation: Any | None) -> str | None:
    if observation is None:
        return None
    summary = getattr(observation, "visible_text_summary", None)
    if summary is None and isinstance(observation, dict):
        summary = observation.get("visible_text_summary")
    if summary is None:
        return None
    text = str(summary)
    return text if len(text) <= 500 else text[:500].rstrip()


def _observation_has_expected(
    observation: PageObservation | None,
    expected_content: str | None,
) -> bool:
    if not expected_content or observation is None:
        return False
    summary = observation.visible_text_summary.lower()
    return expected_content.lower() in summary


async def _safe_observe(observe_fn: ObserveFn) -> PageObservation | None:
    try:
        return await _call(observe_fn)
    except Exception:
        return None


def _finish_attempt(
    attempt: RecoveryAttempt,
    page: Page,
    status: str,
    reason: str,
    observation: PageObservation | None = None,
    metadata: dict[str, Any] | None = None,
) -> RecoveryAttempt:
    return attempt.model_copy(
        update={
            "status": status,
            "reason": reason,
            "after_url": _safe_page_url(page),
            "after_observation_summary": _observation_summary(observation),
            "metadata": metadata or {},
        }
    )


async def _call(fn: Callable[..., Any]) -> Any:
    value = fn()
    if inspect.isawaitable(value):
        return await value
    return value


async def _call_with_optional_arg(fn: ExecuteClickFn, arg: Any | None) -> Any:
    if arg is None:
        return await _call(fn)
    try:
        value = fn(arg)
    except TypeError:
        value = fn()
    if inspect.isawaitable(value):
        return await value
    return value


def _safe_page_url(page: Page) -> str | None:
    try:
        return page.url
    except Exception:
        return None


def _write_attempt(
    trace_recorder: TraceRecorder | None,
    attempt: RecoveryAttempt,
) -> None:
    if trace_recorder is None:
        return
    path = trace_recorder.run_dir / "recovery.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(attempt.model_dump(mode="json"), ensure_ascii=False))
        file.write("\n")


def _record_trace(
    trace_recorder: TraceRecorder | None,
    attempt: RecoveryAttempt,
    action_type: str,
    status: str,
) -> None:
    if trace_recorder is None:
        return
    trace_recorder.record(
        TraceStep(
            step_id=attempt.attempt_id,
            run_id=trace_recorder.run_id,
            phase="browser_recovery",
            actor="system",
            action_type=action_type,
            status=status,
            url_before=attempt.before_url,
            url_after=attempt.after_url,
            observation=attempt.model_dump(mode="json"),
            error_type=attempt.error_type.value,
            error_message=attempt.reason if status not in {"succeeded", "running"} else None,
        )
    )


def _emit(
    event_sink: TaskEventSink | None,
    transcript_store: TranscriptStore | None,
    event_type: str,
    message: str,
    task_id: str | None,
    payload: dict[str, Any],
) -> None:
    safe_payload = json.loads(json.dumps(payload, ensure_ascii=False, default=str))
    if transcript_store is not None:
        try:
            transcript_store.append(event_type, safe_payload)
        except Exception:
            pass
    if event_sink is not None and task_id is not None:
        try:
            event_sink(event_type, message, safe_payload)
        except Exception:
            pass


def _emit_result(
    event_sink: TaskEventSink | None,
    transcript_store: TranscriptStore | None,
    task_id: str | None,
    result: RecoveryResult,
) -> None:
    if result.blocked:
        event_type = "recovery_blocked"
        message = "Recovery blocked"
    elif result.recovered:
        event_type = "recovery_succeeded"
        message = "Recovery succeeded"
    else:
        event_type = "recovery_failed"
        message = "Recovery failed"
    _emit(
        event_sink,
        transcript_store,
        event_type,
        message,
        task_id,
        {
            "recovered": result.recovered,
            "blocked": result.blocked,
            "attempts": len(result.attempts),
            "final_error_type": result.final_error_type.value
            if result.final_error_type is not None
            else None,
            "message": result.message,
        },
    )


def _add_recovery_evidence(
    evidence_store: EvidenceStore | None,
    result: RecoveryResult,
    attempt: RecoveryAttempt,
) -> None:
    if evidence_store is None:
        return
    try:
        evidence_store.add_item(
            kind="action_result",
            source_url=attempt.after_url,
            text=result.message,
            metadata={
                "recovery_result": result.model_dump(mode="json"),
                "recovery_attempt": attempt.model_dump(mode="json"),
            },
        )
        evidence_store.write_jsonl()
    except Exception:
        return


def _dump_model(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, (list, tuple)):
        return [_dump_model(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _dump_model(item) for key, item in value.items()}
    return str(value)


async def default_observe_with_screenshot(
    page: Page,
    path: Path | None = None,
) -> PageObservation:
    return await observe_page(page, screenshot_path=path)
