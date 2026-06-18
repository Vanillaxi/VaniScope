from __future__ import annotations

from typing import Any

from webscoper.schemas.observation import PageObservation
from webscoper.schemas.recovery import RecoveryErrorType


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
