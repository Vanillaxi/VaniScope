from __future__ import annotations

from webscoper.browser.recovery import RecoveryManager
from webscoper.browser.recovery.manager import RecoveryManager as ManagerImport
from webscoper.browser.recovery.planner import RecoveryPlanner
from webscoper.schemas.browser import ActionResult, EffectVerificationResult
from webscoper.schemas.browser import PageObservation, RiskSignal
from webscoper.schemas.browser import RecoveryErrorType, RecoveryStrategy


def test_recovery_manager_public_import_remains_available() -> None:
    assert RecoveryManager is ManagerImport


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


def test_hydrating_target_uses_readiness_retry_plan() -> None:
    manager = RecoveryManager()
    result = ActionResult(
        action_type="click",
        status="failed",
        error_type="TARGET_DISABLED_PENDING_HYDRATION",
        error_message="The target is visible but disabled while hydration finishes.",
    )

    error_type = manager.classify_failure(action_result=result)
    plan = manager.build_plan(error_type)

    assert error_type == RecoveryErrorType.TARGET_DISABLED_PENDING_HYDRATION
    assert RecoveryStrategy.WAIT_AND_REOBSERVE in plan.strategies
    assert RecoveryStrategy.RETRY_AFTER_READY in plan.strategies


def test_overlay_blocking_action_uses_overlay_strategy() -> None:
    manager = RecoveryManager()
    result = ActionResult(
        action_type="click",
        status="failed",
        error_type="TARGET_COVERED_BY_OVERLAY",
        error_message="A blocking overlay or modal covers the page.",
    )

    error_type = manager.classify_failure(action_result=result)
    plan = manager.build_plan(error_type)

    assert error_type == RecoveryErrorType.TARGET_COVERED_BY_OVERLAY
    assert plan.strategies[0] == RecoveryStrategy.CLICK_AFTER_OVERLAY_GONE


def test_recovery_planner_core_strategy_mapping() -> None:
    planner = RecoveryPlanner()

    assert planner.build_plan(RecoveryErrorType.TARGET_NOT_FOUND).strategies == [
        RecoveryStrategy.WAIT_AND_REOBSERVE,
        RecoveryStrategy.SCROLL_AND_REOBSERVE,
        RecoveryStrategy.RETRY_ALTERNATIVE_TARGET,
    ]
    assert planner.build_plan(RecoveryErrorType.TARGET_COVERED).strategies == [
        RecoveryStrategy.CLOSE_MODAL_IF_SAFE,
        RecoveryStrategy.SCROLL_AND_REOBSERVE,
        RecoveryStrategy.RETRY_SAME_TARGET,
    ]
    assert planner.build_plan(RecoveryErrorType.LOGIN_REQUIRED).strategies == [
        RecoveryStrategy.ABORT_AS_BLOCKED
    ]
