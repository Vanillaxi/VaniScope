from __future__ import annotations

import json
from datetime import UTC, datetime
from enum import StrEnum
from itertools import count
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class ExpectedEffect(BaseModel):
    type: str = Field(default="none")
    value: str | None = None


class ActionContract(BaseModel):
    action_type: str
    intent: str
    target_hint: str
    preferred_roles: list[str] = Field(default_factory=list)
    preconditions: list[str] = Field(default_factory=list)
    expected_effect: ExpectedEffect = Field(default_factory=ExpectedEffect)
    risk_level: str = "read_only"


class TargetCandidate(BaseModel):
    strategy: str
    locator_hint: str
    role: str | None = None
    name: str | None = None
    text: str | None = None
    visible: bool = False
    enabled: bool = False
    bbox: dict[str, float] | None = None
    score: float = 0.0


class ResolvedTarget(BaseModel):
    target_hint: str
    selected: TargetCandidate | None = None
    candidates: list[TargetCandidate] = Field(default_factory=list)
    confidence: float = 0.0
    error_type: str | None = None
    error_message: str | None = None


class ActionResult(BaseModel):
    action_type: str
    status: str
    target: ResolvedTarget | None = None
    url_before: str | None = None
    url_after: str | None = None
    error_type: str | None = None
    error_message: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class EffectVerificationResult(BaseModel):
    status: str
    effect_type: str
    expected_value: str | None = None
    satisfied: bool
    url_before: str | None = None
    url_after: str | None = None
    error_type: str | None = None
    message: str | None = None


class InteractiveElement(BaseModel):
    tag: str
    role: str | None = None
    name: str
    text: str
    locator_hint: str | None = None
    visible: bool
    enabled: bool
    bbox: dict[str, float] | None = None
    confidence: float


class RiskSignal(BaseModel):
    risk_type: str
    message: str
    severity: str


class PageObservation(BaseModel):
    url: str
    title: str
    visible_text_summary: str
    interactive_elements: list[InteractiveElement]
    risk_signals: list[RiskSignal]
    screenshot_path: str | None = None


_RECOVERY_ID_COUNTER = count(1)


class RecoveryErrorType(StrEnum):
    TARGET_NOT_FOUND = "target_not_found"
    TARGET_AMBIGUOUS = "target_ambiguous"
    TARGET_DISABLED = "target_disabled"
    TARGET_COVERED = "target_covered"
    ACTION_NO_EFFECT = "action_no_effect"
    POSTCONDITION_FAILED = "postcondition_failed"
    NAVIGATION_TIMEOUT = "navigation_timeout"
    LAZY_CONTENT_NOT_READY = "lazy_content_not_ready"
    LOGIN_REQUIRED = "login_required"
    CAPTCHA_DETECTED = "captcha_detected"
    RISKY_ACTION_BLOCKED = "risky_action_blocked"
    UNKNOWN = "unknown"


class RecoveryStrategy(StrEnum):
    WAIT_AND_REOBSERVE = "wait_and_reobserve"
    SCROLL_AND_REOBSERVE = "scroll_and_reobserve"
    RETRY_SAME_TARGET = "retry_same_target"
    RETRY_ALTERNATIVE_TARGET = "retry_alternative_target"
    CLOSE_MODAL_IF_SAFE = "close_modal_if_safe"
    OPEN_HREF_DIRECTLY = "open_href_directly"
    ABORT_AS_BLOCKED = "abort_as_blocked"
    ABORT_AS_FAILED = "abort_as_failed"


RecoveryAttemptStatus = Literal[
    "planned",
    "running",
    "succeeded",
    "failed",
    "skipped",
    "blocked",
]


def next_recovery_attempt_id() -> str:
    return f"rec_{next(_RECOVERY_ID_COUNTER):06d}"


def recovery_utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


class RecoveryAttempt(BaseModel):
    attempt_id: str = Field(default_factory=next_recovery_attempt_id)
    task_id: str | None = None
    step_index: int
    error_type: RecoveryErrorType
    strategy: RecoveryStrategy
    status: RecoveryAttemptStatus
    reason: str
    before_url: str | None = None
    after_url: str | None = None
    before_observation_summary: str | None = None
    after_observation_summary: str | None = None
    created_at: str = Field(default_factory=recovery_utc_now_iso)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("metadata")
    @classmethod
    def metadata_must_be_json_serializable(
        cls,
        value: dict[str, Any],
    ) -> dict[str, Any]:
        return json.loads(json.dumps(value, ensure_ascii=False, default=str))


class RecoveryPlan(BaseModel):
    error_type: RecoveryErrorType
    strategies: list[RecoveryStrategy]
    max_attempts: int
    reason: str


class RecoveryResult(BaseModel):
    recovered: bool
    blocked: bool
    final_error_type: RecoveryErrorType | None = None
    attempts: list[RecoveryAttempt] = Field(default_factory=list)
    message: str
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("metadata")
    @classmethod
    def metadata_must_be_json_serializable(
        cls,
        value: dict[str, Any],
    ) -> dict[str, Any]:
        return json.loads(json.dumps(value, ensure_ascii=False, default=str))
