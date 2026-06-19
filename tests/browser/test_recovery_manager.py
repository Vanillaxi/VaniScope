from __future__ import annotations

from webscoper.browser.recovery import RecoveryManager
from webscoper.schemas.browser import ActionResult, EffectVerificationResult
from webscoper.schemas.browser import PageObservation, RiskSignal
from webscoper.schemas.browser import RecoveryErrorType, RecoveryStrategy


def test_recovery_manager_classifies_target_not_found() -> None:
    result = ActionResult(
        action_type="click",
        status="failed",
        error_type="TARGET_NOT_FOUND",
        error_message="No target matched hint: Quickstart",
    )

    assert (
        RecoveryManager().classify_failure(action_result=result)
        == RecoveryErrorType.TARGET_NOT_FOUND
    )


def test_recovery_manager_classifies_postcondition_failed() -> None:
    result = EffectVerificationResult(
        status="failed",
        effect_type="content_appears",
        expected_value="pip install playwright",
        satisfied=False,
        message="Expected content did not appear.",
    )

    assert (
        RecoveryManager().classify_failure(verification_result=result)
        == RecoveryErrorType.POSTCONDITION_FAILED
    )


def test_recovery_manager_blocks_login_and_captcha() -> None:
    manager = RecoveryManager()
    login_observation = PageObservation(
        url="file:///login.html",
        title="Login",
        visible_text_summary="Sign in",
        interactive_elements=[],
        risk_signals=[
            RiskSignal(
                risk_type="login",
                message="Login form detected.",
                severity="medium",
            )
        ],
    )
    captcha_observation = login_observation.model_copy(
        update={
            "risk_signals": [
                RiskSignal(
                    risk_type="captcha",
                    message="Captcha detected.",
                    severity="high",
                )
            ]
        }
    )

    assert (
        manager.classify_failure(observation=login_observation)
        == RecoveryErrorType.LOGIN_REQUIRED
    )
    assert (
        manager.classify_failure(observation=captcha_observation)
        == RecoveryErrorType.CAPTCHA_DETECTED
    )
    assert manager.build_plan(
        RecoveryErrorType.CAPTCHA_DETECTED
    ).strategies == [RecoveryStrategy.ABORT_AS_BLOCKED]


def test_disabled_target_plan_aborts_as_failed() -> None:
    plan = RecoveryManager().build_plan(RecoveryErrorType.TARGET_DISABLED)

    assert plan.strategies == [RecoveryStrategy.ABORT_AS_FAILED]
