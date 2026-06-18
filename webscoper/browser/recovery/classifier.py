from __future__ import annotations

from typing import Any

from webscoper.schemas.observation import PageObservation
from webscoper.schemas.action import ActionResult, EffectVerificationResult
from webscoper.schemas.recovery import RecoveryErrorType


class RecoveryClassifier:
    def classify_failure(
        self,
        *,
        error: Exception | None = None,
        action_result: ActionResult | Any | None = None,
        verification_result: EffectVerificationResult | Any | None = None,
        observation: Any | None = None,
        target_hint: str | None = None,
    ) -> RecoveryErrorType:
        risk_type = risk_error_type(observation)
        if risk_type is not None:
            return risk_type

        if action_result is not None:
            action_error = normalized_error_text(
                getattr(action_result, "error_type", None)
            )
            action_message = normalized_error_text(
                getattr(action_result, "error_message", None)
            )
            combined = f"{action_error} {action_message}".strip()
            if "target_not_found" in action_error or "target not found" in combined:
                return RecoveryErrorType.TARGET_NOT_FOUND
            if "target_ambiguous" in action_error or "ambiguous" in combined:
                return RecoveryErrorType.TARGET_AMBIGUOUS
            if "target_disabled" in action_error or "disabled" in combined:
                return RecoveryErrorType.TARGET_DISABLED
            if looks_covered(combined):
                return RecoveryErrorType.TARGET_COVERED
            if "timeout" in combined:
                return RecoveryErrorType.NAVIGATION_TIMEOUT

        if verification_result is not None:
            satisfied = bool(getattr(verification_result, "satisfied", False))
            if not satisfied:
                error_type = normalized_error_text(
                    getattr(verification_result, "error_type", None)
                )
                message = normalized_error_text(
                    getattr(verification_result, "message", None)
                )
                if "timeout" in error_type or "timeout" in message:
                    return RecoveryErrorType.NAVIGATION_TIMEOUT
                if "no url or page text change" in message:
                    return RecoveryErrorType.ACTION_NO_EFFECT
                return RecoveryErrorType.POSTCONDITION_FAILED

        if error is not None:
            message = normalized_error_text(str(error))
            if looks_covered(message):
                return RecoveryErrorType.TARGET_COVERED
            if "timeout" in type(error).__name__.lower() or "timeout" in message:
                return RecoveryErrorType.NAVIGATION_TIMEOUT

        if target_hint and observation is not None:
            summary = normalized_error_text(observation_summary(observation))
            if target_hint.lower() not in summary:
                return RecoveryErrorType.TARGET_NOT_FOUND

        return RecoveryErrorType.UNKNOWN


def risk_error_type(observation: Any | None) -> RecoveryErrorType | None:
    signals = getattr(observation, "risk_signals", []) or []
    risk_types = {str(getattr(signal, "risk_type", "")).lower() for signal in signals}
    if "captcha" in risk_types:
        return RecoveryErrorType.CAPTCHA_DETECTED
    if "login" in risk_types or "password" in risk_types:
        return RecoveryErrorType.LOGIN_REQUIRED
    return None


def looks_covered(value: str) -> bool:
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


def normalized_error_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).replace("_", " ").lower()


def observation_summary(observation: Any | None) -> str | None:
    if observation is None:
        return None
    summary = getattr(observation, "visible_text_summary", None)
    if summary is None and isinstance(observation, dict):
        summary = observation.get("visible_text_summary")
    if summary is None:
        return None
    text = str(summary)
    return text if len(text) <= 500 else text[:500].rstrip()


def observation_has_expected(
    observation: PageObservation | None,
    expected_content: str | None,
) -> bool:
    if not expected_content or observation is None:
        return False
    summary = observation.visible_text_summary.lower()
    return expected_content.lower() in summary
