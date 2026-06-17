from __future__ import annotations

import json
from enum import StrEnum
from itertools import count
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


_FINDING_ID_COUNTER = count(1)
_ACTION_ID_COUNTER = count(1)
_PLAN_ID_COUNTER = count(1)


class ReviewerMode(StrEnum):
    DETERMINISTIC = "deterministic"
    FAKE_LLM = "fake_llm"
    REAL_LLM = "real_llm"


class LLMReviewRequest(BaseModel):
    task_id: str | None = None
    task_goal: str | None = None
    report_markdown: str
    evidence_items: list[dict[str, Any]] = Field(default_factory=list)
    compact_context: dict[str, Any] | None = None
    deterministic_review: dict[str, Any] | None = None
    instructions: list[str] = Field(default_factory=list)


class LLMReviewFinding(BaseModel):
    finding_id: str = Field(default_factory=lambda: f"finding_{next(_FINDING_ID_COUNTER):06d}")
    severity: Literal["info", "warning", "error"]
    issue_type: str
    message: str
    evidence_ids: list[str] = Field(default_factory=list)
    suggested_fix: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("metadata")
    @classmethod
    def metadata_must_be_json_serializable(
        cls,
        value: dict[str, Any],
    ) -> dict[str, Any]:
        return _json_safe(value)


class LLMReviewResult(BaseModel):
    passed: bool
    score: float
    findings: list[LLMReviewFinding] = Field(default_factory=list)
    summary: str
    raw_response: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("metadata")
    @classmethod
    def metadata_must_be_json_serializable(
        cls,
        value: dict[str, Any],
    ) -> dict[str, Any]:
        return _json_safe(value)


class RevisionAction(BaseModel):
    action_id: str = Field(default_factory=lambda: f"revact_{next(_ACTION_ID_COUNTER):06d}")
    action_type: Literal[
        "add_evidence_reference",
        "remove_unsupported_claim",
        "rewrite_claim",
        "add_missing_result",
        "add_missing_evidence_section",
        "no_op",
    ]
    target: str | None = None
    replacement: str | None = None
    evidence_ids: list[str] = Field(default_factory=list)
    reason: str
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("metadata")
    @classmethod
    def metadata_must_be_json_serializable(
        cls,
        value: dict[str, Any],
    ) -> dict[str, Any]:
        return _json_safe(value)


class RevisionPlan(BaseModel):
    plan_id: str = Field(default_factory=lambda: f"revplan_{next(_PLAN_ID_COUNTER):06d}")
    actions: list[RevisionAction] = Field(default_factory=list)
    summary: str
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("metadata")
    @classmethod
    def metadata_must_be_json_serializable(
        cls,
        value: dict[str, Any],
    ) -> dict[str, Any]:
        return _json_safe(value)


class RevisionResult(BaseModel):
    revised: bool
    revised_report_markdown: str
    applied_actions: list[RevisionAction] = Field(default_factory=list)
    skipped_actions: list[RevisionAction] = Field(default_factory=list)
    summary: str
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("metadata")
    @classmethod
    def metadata_must_be_json_serializable(
        cls,
        value: dict[str, Any],
    ) -> dict[str, Any]:
        return _json_safe(value)


class ReviseLoopResult(BaseModel):
    task_id: str | None = None
    initial_review: dict[str, Any]
    llm_review: LLMReviewResult | None = None
    revision_plan: RevisionPlan
    revision_result: RevisionResult
    final_review: dict[str, Any]
    passed: bool
    artifacts: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("metadata")
    @classmethod
    def metadata_must_be_json_serializable(
        cls,
        value: dict[str, Any],
    ) -> dict[str, Any]:
        return _json_safe(value)


def _json_safe(payload: dict[str, Any]) -> dict[str, Any]:
    return json.loads(json.dumps(payload, ensure_ascii=False, default=str))
