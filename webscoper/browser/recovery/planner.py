from __future__ import annotations

from typing import Any

from webscoper.schemas.browser import (
    RecoveryErrorType,
    RecoveryPlan,
    RecoveryStrategy,
)


class RecoveryPlanner:
    def __init__(self, max_attempts: int = 2) -> None:
        self.max_attempts = max(1, max_attempts)

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
