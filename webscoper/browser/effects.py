from __future__ import annotations

from playwright.async_api import Page

from webscoper.schemas.action import EffectVerificationResult, ExpectedEffect


class EffectVerifier:
    async def verify(
        self,
        page: Page,
        expected: ExpectedEffect,
        url_before: str | None,
        body_text_before: str | None = None,
    ) -> EffectVerificationResult:
        effect_type = expected.type
        url_after = page.url

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
                body_text_after = await _body_text(page)
                satisfied = expected.value.lower() in body_text_after.lower()
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
                satisfied = bool(url_before) and url_after != url_before
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
                satisfied = expected.value in url_after
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
                body_text_after = await _body_text(page)
                body_changed = (
                    body_text_before is not None and body_text_after != body_text_before
                )
                url_changed = bool(url_before) and url_after != url_before
                satisfied = url_changed or body_changed
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


async def _body_text(page: Page) -> str:
    try:
        return await page.locator("body").inner_text(timeout=3000)
    except Exception:
        return ""


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
