from __future__ import annotations

import inspect
from pathlib import Path
from typing import Any, Awaitable, Callable

from playwright.async_api import Page

from webscoper.browser.observer import observe_page
from webscoper.browser.recovery.classifier import (
    observation_has_expected,
    observation_summary,
    risk_error_type,
)
from webscoper.schemas.browser import ActionResult, EffectVerificationResult
from webscoper.schemas.browser import PageObservation
from webscoper.schemas.browser import RecoveryAttempt, RecoveryStrategy


ObserveFn = Callable[[], Awaitable[PageObservation] | PageObservation]
ResolveFn = Callable[[], Awaitable[Any] | Any]
ExecuteClickFn = Callable[..., Awaitable[ActionResult] | ActionResult]
VerifyFn = Callable[[], Awaitable[EffectVerificationResult] | EffectVerificationResult]


class RecoveryStrategies:
    async def run(
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
                return await self.abort_as_blocked(page=page, attempt=attempt)
            if strategy == RecoveryStrategy.ABORT_AS_FAILED:
                return await self.abort_as_failed(page=page, attempt=attempt)
            if strategy == RecoveryStrategy.WAIT_AND_REOBSERVE:
                return await self.wait_and_reobserve(
                    page=page,
                    attempt=attempt,
                    expected_content=expected_content,
                    observe_fn=observe_fn,
                    resolve_fn=resolve_fn,
                    execute_click_fn=execute_click_fn,
                    verify_fn=verify_fn,
                )
            if strategy == RecoveryStrategy.SCROLL_AND_REOBSERVE:
                return await self.scroll_and_reobserve(
                    page=page,
                    attempt=attempt,
                    observe_fn=observe_fn,
                    resolve_fn=resolve_fn,
                    execute_click_fn=execute_click_fn,
                    verify_fn=verify_fn,
                )
            if strategy == RecoveryStrategy.RETRY_SAME_TARGET:
                return await self.retry_same_target(
                    page=page,
                    attempt=attempt,
                    observe_fn=observe_fn,
                    resolve_fn=resolve_fn,
                    execute_click_fn=execute_click_fn,
                    verify_fn=verify_fn,
                )
            if strategy == RecoveryStrategy.RETRY_ALTERNATIVE_TARGET:
                return await self.retry_alternative_target(
                    page=page,
                    attempt=attempt,
                    observe_fn=observe_fn,
                    resolve_fn=resolve_fn,
                    execute_click_fn=execute_click_fn,
                    verify_fn=verify_fn,
                )
            if strategy == RecoveryStrategy.CLOSE_MODAL_IF_SAFE:
                return await self.close_modal_if_safe(
                    page=page,
                    attempt=attempt,
                    observe_fn=observe_fn,
                    resolve_fn=resolve_fn,
                    execute_click_fn=execute_click_fn,
                    verify_fn=verify_fn,
                )
            if strategy == RecoveryStrategy.OPEN_HREF_DIRECTLY:
                return await self.open_href_directly(
                    page=page,
                    attempt=attempt,
                    observe_fn=observe_fn,
                )
        except Exception as exc:
            observation = await safe_observe(observe_fn)
            return finish_attempt(
                attempt,
                page,
                "failed",
                f"Recovery attempt raised {type(exc).__name__}: {exc}",
                observation,
                {"exception_type": type(exc).__name__},
            )

        observation = await safe_observe(observe_fn)
        return finish_attempt(
            attempt,
            page,
            "failed",
            "Recovery strategy was not handled.",
            observation,
        )

    async def wait_and_reobserve(
        self,
        *,
        page: Page,
        attempt: RecoveryAttempt,
        expected_content: str | None,
        observe_fn: ObserveFn,
        resolve_fn: ResolveFn,
        execute_click_fn: ExecuteClickFn,
        verify_fn: VerifyFn,
    ) -> RecoveryAttempt:
        await page.wait_for_timeout(800)
        observation = await call(observe_fn)
        risk_type = risk_error_type(observation)
        if risk_type is not None:
            return finish_attempt(
                attempt,
                page,
                "blocked",
                f"Recovery blocked by {risk_type.value}.",
                observation,
                {"risk_type": risk_type.value},
            )
        if observation_has_expected(observation, expected_content):
            return finish_attempt(
                attempt,
                page,
                "succeeded",
                "Expected content appeared after waiting.",
                observation,
            )
        return await retry_click_and_verify(
            page=page,
            attempt=attempt,
            observe_fn=observe_fn,
            resolve_fn=resolve_fn,
            execute_click_fn=execute_click_fn,
            verify_fn=verify_fn,
            fallback_reason="Target was still unavailable after waiting.",
        )

    async def scroll_and_reobserve(
        self,
        *,
        page: Page,
        attempt: RecoveryAttempt,
        observe_fn: ObserveFn,
        resolve_fn: ResolveFn,
        execute_click_fn: ExecuteClickFn,
        verify_fn: VerifyFn,
    ) -> RecoveryAttempt:
        await page.evaluate("() => window.scrollBy(0, Math.max(300, window.innerHeight / 2))")
        await page.wait_for_timeout(250)
        return await retry_click_and_verify(
            page=page,
            attempt=attempt,
            observe_fn=observe_fn,
            resolve_fn=resolve_fn,
            execute_click_fn=execute_click_fn,
            verify_fn=verify_fn,
            fallback_reason="Retry after scroll did not satisfy the expected effect.",
        )

    async def retry_same_target(
        self,
        *,
        page: Page,
        attempt: RecoveryAttempt,
        observe_fn: ObserveFn,
        resolve_fn: ResolveFn,
        execute_click_fn: ExecuteClickFn,
        verify_fn: VerifyFn,
    ) -> RecoveryAttempt:
        return await retry_click_and_verify(
            page=page,
            attempt=attempt,
            observe_fn=observe_fn,
            resolve_fn=resolve_fn,
            execute_click_fn=execute_click_fn,
            verify_fn=verify_fn,
            fallback_reason="Retrying the same target did not satisfy the expected effect.",
        )

    async def retry_alternative_target(
        self,
        *,
        page: Page,
        attempt: RecoveryAttempt,
        observe_fn: ObserveFn,
        resolve_fn: ResolveFn,
        execute_click_fn: ExecuteClickFn,
        verify_fn: VerifyFn,
    ) -> RecoveryAttempt:
        resolved = await call(resolve_fn)
        candidates = list(getattr(resolved, "candidates", []) or [])
        if len(candidates) < 2:
            observation = await call(observe_fn)
            return finish_attempt(
                attempt,
                page,
                "failed",
                "No alternative target candidate was available.",
                observation,
                {"candidate_count": len(candidates)},
            )
        return await retry_click_and_verify(
            page=page,
            attempt=attempt,
            observe_fn=observe_fn,
            resolve_fn=resolve_fn,
            execute_click_fn=execute_click_fn,
            verify_fn=verify_fn,
            fallback_reason="Alternative target retry failed.",
            candidate=candidates[1],
        )

    async def close_modal_if_safe(
        self,
        *,
        page: Page,
        attempt: RecoveryAttempt,
        observe_fn: ObserveFn,
        resolve_fn: ResolveFn,
        execute_click_fn: ExecuteClickFn,
        verify_fn: VerifyFn,
    ) -> RecoveryAttempt:
        closed = await close_safe_modal_control(page)
        observation = await call(observe_fn)
        if not closed:
            return finish_attempt(
                attempt,
                page,
                "failed",
                "No safe modal close control was found.",
                observation,
            )
        return await retry_click_and_verify(
            page=page,
            attempt=attempt,
            observe_fn=observe_fn,
            resolve_fn=resolve_fn,
            execute_click_fn=execute_click_fn,
            verify_fn=verify_fn,
            fallback_reason="Target retry after closing modal failed.",
            metadata={"closed_modal": True},
        )

    async def open_href_directly(
        self,
        *,
        page: Page,
        attempt: RecoveryAttempt,
        observe_fn: ObserveFn,
    ) -> RecoveryAttempt:
        observation = await call(observe_fn)
        return finish_attempt(
            attempt,
            page,
            "skipped",
            "Opening href directly is not enabled in the MVP.",
            observation,
        )

    async def abort_as_blocked(
        self,
        *,
        page: Page,
        attempt: RecoveryAttempt,
    ) -> RecoveryAttempt:
        return finish_attempt(
            attempt,
            page,
            "blocked",
            "Recovery blocked by login, captcha, or risk signal.",
        )

    async def abort_as_failed(
        self,
        *,
        page: Page,
        attempt: RecoveryAttempt,
    ) -> RecoveryAttempt:
        return finish_attempt(
            attempt,
            page,
            "failed",
            "Recovery aborted; no safe retry is available.",
        )


async def retry_click_and_verify(
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
    resolved = await call(resolve_fn)
    action_result = await call_with_optional_arg(execute_click_fn, candidate)
    verification_result = await call(verify_fn)
    observation = await call(observe_fn)
    attempt_metadata = {
        "resolved": dump_model(resolved),
        "action_result": dump_model(action_result),
        "verification_result": dump_model(verification_result),
    }
    if metadata:
        attempt_metadata.update(metadata)
    if candidate is not None:
        attempt_metadata["candidate"] = dump_model(candidate)
    if getattr(action_result, "status", None) == "success" and bool(
        getattr(verification_result, "satisfied", False)
    ):
        return finish_attempt(
            attempt,
            page,
            "succeeded",
            "Retry satisfied the expected effect.",
            observation,
            attempt_metadata,
        )
    return finish_attempt(
        attempt,
        page,
        "failed",
        fallback_reason,
        observation,
        attempt_metadata,
    )


async def close_safe_modal_control(page: Page) -> bool:
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


async def safe_observe(observe_fn: ObserveFn) -> PageObservation | None:
    try:
        return await call(observe_fn)
    except Exception:
        return None


def finish_attempt(
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
            "after_url": safe_page_url(page),
            "after_observation_summary": observation_summary(observation),
            "metadata": metadata or {},
        }
    )


async def call(fn: Callable[..., Any]) -> Any:
    value = fn()
    if inspect.isawaitable(value):
        return await value
    return value


async def call_with_optional_arg(fn: ExecuteClickFn, arg: Any | None) -> Any:
    if arg is None:
        return await call(fn)
    try:
        value = fn(arg)
    except TypeError:
        value = fn()
    if inspect.isawaitable(value):
        return await value
    return value


def safe_page_url(page: Page) -> str | None:
    try:
        return page.url
    except Exception:
        return None


def dump_model(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, (list, tuple)):
        return [dump_model(item) for item in value]
    if isinstance(value, dict):
        return {str(key): dump_model(item) for key, item in value.items()}
    return str(value)


async def default_observe_with_screenshot(
    page: Page,
    path: Path | None = None,
) -> PageObservation:
    return await observe_page(page, screenshot_path=path)
