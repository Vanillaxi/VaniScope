from __future__ import annotations

from time import monotonic

from playwright.async_api import Page

from webscoper.schemas.action import EffectVerificationResult, ExpectedEffect


class EffectVerifier:
    async def verify(
        self,
        page: Page,
        expected: ExpectedEffect,
        url_before: str | None,
        body_text_before: str | None = None,
        timeout_ms: int = 2000,
        interval_ms: int = 100,
    ) -> EffectVerificationResult:
        effect_type = expected.type
        url_after = _safe_url(page)

        try:
            if effect_type == "none":
                return EffectVerificationResult(
                    status="success",
                    effect_type=effect_type,
                    expected_value=expected.value,
                    satisfied=True,
                    url_before=url_before,
                    url_after=url_after,
                    message="No effect required.",
                )

            if effect_type == "content_appears":
                if not expected.value:
                    return _missing_value_result(effect_type, url_before, url_after)
                satisfied = False
                url_after = _safe_url(page)
                expected_text = expected.value.lower()
                async for snapshot in _poll_page(page, timeout_ms, interval_ms):
                    url_after = snapshot.url
                    if snapshot.error is not None:
                        return _read_failed_result(
                            effect_type,
                            expected.value,
                            url_before,
                            url_after,
                            snapshot.error,
                        )
                    if expected_text in snapshot.body_text.lower():
                        satisfied = True
                        break
                return EffectVerificationResult(
                    status="success" if satisfied else "failed",
                    effect_type=effect_type,
                    expected_value=expected.value,
                    satisfied=satisfied,
                    url_before=url_before,
                    url_after=url_after,
                    message=(
                        "Expected content appeared."
                        if satisfied
                        else "Expected content did not appear."
                    ),
                )

            if effect_type == "url_changes":
                satisfied = False
                async for snapshot in _poll_page(page, timeout_ms, interval_ms):
                    url_after = snapshot.url
                    if snapshot.error is not None:
                        return _read_failed_result(
                            effect_type,
                            expected.value,
                            url_before,
                            url_after,
                            snapshot.error,
                        )
                    if bool(url_before) and snapshot.url != url_before:
                        satisfied = True
                        break
                return EffectVerificationResult(
                    status="success" if satisfied else "failed",
                    effect_type=effect_type,
                    expected_value=expected.value,
                    satisfied=satisfied,
                    url_before=url_before,
                    url_after=url_after,
                    message="URL changed." if satisfied else "URL did not change.",
                )

            if effect_type == "url_contains":
                if not expected.value:
                    return _missing_value_result(effect_type, url_before, url_after)
                satisfied = False
                async for snapshot in _poll_page(page, timeout_ms, interval_ms):
                    url_after = snapshot.url
                    if snapshot.error is not None:
                        return _read_failed_result(
                            effect_type,
                            expected.value,
                            url_before,
                            url_after,
                            snapshot.error,
                        )
                    if expected.value in snapshot.url:
                        satisfied = True
                        break
                return EffectVerificationResult(
                    status="success" if satisfied else "failed",
                    effect_type=effect_type,
                    expected_value=expected.value,
                    satisfied=satisfied,
                    url_before=url_before,
                    url_after=url_after,
                    message=(
                        "URL contains expected value."
                        if satisfied
                        else "URL does not contain expected value."
                    ),
                )

            if effect_type == "any_change":
                satisfied = False
                async for snapshot in _poll_page(page, timeout_ms, interval_ms):
                    url_after = snapshot.url
                    if snapshot.error is not None:
                        return _read_failed_result(
                            effect_type,
                            expected.value,
                            url_before,
                            url_after,
                            snapshot.error,
                        )
                    body_changed = (
                        body_text_before is not None
                        and snapshot.body_text != body_text_before
                    )
                    url_changed = bool(url_before) and snapshot.url != url_before
                    if url_changed or body_changed:
                        satisfied = True
                        break
                return EffectVerificationResult(
                    status="success" if satisfied else "failed",
                    effect_type=effect_type,
                    expected_value=expected.value,
                    satisfied=satisfied,
                    url_before=url_before,
                    url_after=url_after,
                    message=(
                        "URL or page text changed."
                        if satisfied
                        else "No URL or page text change detected."
                    ),
                )

            return EffectVerificationResult(
                status="failed",
                effect_type=effect_type,
                expected_value=expected.value,
                satisfied=False,
                url_before=url_before,
                url_after=url_after,
                error_type="UNSUPPORTED_EFFECT_TYPE",
                message=f"Unsupported expected effect type: {effect_type}",
            )
        except Exception as exc:
            return EffectVerificationResult(
                status="failed",
                effect_type=effect_type,
                expected_value=expected.value,
                satisfied=False,
                url_before=url_before,
                url_after=url_after,
                error_type=type(exc).__name__,
                message=str(exc),
            )


class _PageSnapshot:
    def __init__(
        self,
        url: str | None,
        body_text: str,
        error: Exception | None = None,
    ) -> None:
        self.url = url
        self.body_text = body_text
        self.error = error


async def _poll_page(page: Page, timeout_ms: int, interval_ms: int):
    deadline = monotonic() + max(timeout_ms, 0) / 1000
    interval = max(interval_ms, 1)

    while True:
        try:
            yield _PageSnapshot(url=_safe_url(page), body_text=await _body_text(page))
        except Exception as exc:
            yield _PageSnapshot(url=_safe_url(page), body_text="", error=exc)
            return

        if monotonic() >= deadline:
            return
        await page.wait_for_timeout(interval)


async def _body_text(page: Page) -> str:
    return await page.locator("body").inner_text(timeout=1000)


def _safe_url(page: Page) -> str | None:
    try:
        return page.url
    except Exception:
        return None


def _missing_value_result(
    effect_type: str,
    url_before: str | None,
    url_after: str | None,
) -> EffectVerificationResult:
    return EffectVerificationResult(
        status="failed",
        effect_type=effect_type,
        expected_value=None,
        satisfied=False,
        url_before=url_before,
        url_after=url_after,
        error_type="EXPECTED_VALUE_REQUIRED",
        message=f"Effect type {effect_type} requires expected.value.",
    )


def _read_failed_result(
    effect_type: str,
    expected_value: str | None,
    url_before: str | None,
    url_after: str | None,
    error: Exception,
) -> EffectVerificationResult:
    return EffectVerificationResult(
        status="failed",
        effect_type=effect_type,
        expected_value=expected_value,
        satisfied=False,
        url_before=url_before,
        url_after=url_after,
        error_type=type(error).__name__,
        message=str(error),
    )
