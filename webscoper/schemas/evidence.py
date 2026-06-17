from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


EvidenceKind = Literal[
    "page_observation",
    "text_excerpt",
    "action_result",
    "screenshot",
    "tool_result",
]


class EvidenceSource(BaseModel):
    source_url: str | None = None
    page_title: str | None = None
    trace_event_id: str | None = None
    transcript_event_id: str | None = None


class EvidenceItem(BaseModel):
    evidence_id: str
    kind: EvidenceKind
    source_url: str | None = None
    page_title: str | None = None
    text: str | None = None
    screenshot_path: str | None = None
    trace_event_id: str | None = None
    transcript_event_id: str | None = None
    created_at: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class EvidenceStoreRecord(BaseModel):
    item: EvidenceItem
