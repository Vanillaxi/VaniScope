from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


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
