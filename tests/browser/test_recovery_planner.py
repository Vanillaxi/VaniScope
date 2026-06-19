from __future__ import annotations

from webscoper.browser.recovery import RecoveryManager
from webscoper.browser.recovery.manager import RecoveryManager as ManagerImport
from webscoper.browser.recovery.planner import RecoveryPlanner
from webscoper.schemas.browser import RecoveryErrorType, RecoveryStrategy


def test_recovery_manager_public_imports_remain_available() -> None:
    assert RecoveryManager is ManagerImport


def test_recovery_planner_target_not_found_strategy_order() -> None:
    plan = RecoveryPlanner().build_plan(RecoveryErrorType.TARGET_NOT_FOUND)

    assert plan.strategies == [
        RecoveryStrategy.WAIT_AND_REOBSERVE,
        RecoveryStrategy.SCROLL_AND_REOBSERVE,
        RecoveryStrategy.RETRY_ALTERNATIVE_TARGET,
    ]


def test_recovery_planner_target_covered_strategy_order() -> None:
    plan = RecoveryPlanner().build_plan(RecoveryErrorType.TARGET_COVERED)

    assert plan.strategies == [
        RecoveryStrategy.CLOSE_MODAL_IF_SAFE,
        RecoveryStrategy.SCROLL_AND_REOBSERVE,
        RecoveryStrategy.RETRY_SAME_TARGET,
    ]


def test_recovery_planner_human_only_failures_abort_as_blocked() -> None:
    planner = RecoveryPlanner()

    for error_type in [
        RecoveryErrorType.LOGIN_REQUIRED,
        RecoveryErrorType.CAPTCHA_DETECTED,
        RecoveryErrorType.RISKY_ACTION_BLOCKED,
    ]:
        assert planner.build_plan(error_type).strategies == [
            RecoveryStrategy.ABORT_AS_BLOCKED
        ]
