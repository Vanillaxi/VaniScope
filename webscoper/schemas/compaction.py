from __future__ import annotations

import json
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, field_validator


class CompactionTrigger(StrEnum):
    MANUAL = "manual"
    TRANSCRIPT_LIMIT = "transcript_limit"
    TRACE_LIMIT = "trace_limit"
    EVIDENCE_LIMIT = "evidence_limit"
    TASK_FINALIZE = "task_finalize"


class CompactionPolicy(BaseModel):
    max_transcript_events: int = 20
    max_trace_events: int = 30
    max_evidence_items: int = 20
    preserve_recent_events: int = 8
    preserve_failed_steps: bool = True
    preserve_recovery_steps: bool = True
    preserve_risk_events: bool = True
    preserve_approval_events: bool = True


class CompactedStep(BaseModel):
    step_id: str
    source_event_ids: list[str] = Field(default_factory=list)
    kind: str
    summary: str
    evidence_ids: list[str] = Field(default_factory=list)
    source_urls: list[str] = Field(default_factory=list)
    status: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("metadata")
    @classmethod
    def metadata_must_be_json_serializable(
        cls,
        value: dict[str, Any],
    ) -> dict[str, Any]:
        return _json_safe(value)


class CompactedEvidenceRef(BaseModel):
    evidence_id: str
    kind: str
    source_url: str | None = None
    page_title: str | None = None
    text_preview: str | None = None
    screenshot_path: str | None = None


class CompactedBrowserState(BaseModel):
    current_url: str | None = None
    current_title: str | None = None
    last_observation_summary: str | None = None
    visible_text_preview: str | None = None
    screenshot_path: str | None = None


class CompactedRiskState(BaseModel):
    has_pending_approval: bool = False
    pending_approval_ids: list[str] = Field(default_factory=list)
    blocked: bool = False
    risk_signals: list[dict[str, Any]] = Field(default_factory=list)


class CompactedRecoveryState(BaseModel):
    total_attempts: int = 0
    recovered_count: int = 0
    failed_count: int = 0
    blocked_count: int = 0
    recent_attempts: list[dict[str, Any]] = Field(default_factory=list)


class ContextPack(BaseModel):
    task_id: str | None = None
    task_goal: str | None = None
    current_state: CompactedBrowserState | None = None
    key_steps: list[CompactedStep] = Field(default_factory=list)
    recent_steps: list[CompactedStep] = Field(default_factory=list)
    evidence_refs: list[CompactedEvidenceRef] = Field(default_factory=list)
    recovery_state: CompactedRecoveryState | None = None
    risk_state: CompactedRiskState | None = None
    open_questions: list[str] = Field(default_factory=list)
    next_action_hint: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("metadata")
    @classmethod
    def metadata_must_be_json_serializable(
        cls,
        value: dict[str, Any],
    ) -> dict[str, Any]:
        return _json_safe(value)


class CompactionResult(BaseModel):
    compacted: bool
    reason: str
    before_counts: dict[str, int] = Field(default_factory=dict)
    after_counts: dict[str, int] = Field(default_factory=dict)
    context_pack: ContextPack
    warnings: list[str] = Field(default_factory=list)


def _json_safe(payload: dict[str, Any]) -> dict[str, Any]:
    return json.loads(json.dumps(payload, ensure_ascii=False, default=str))
