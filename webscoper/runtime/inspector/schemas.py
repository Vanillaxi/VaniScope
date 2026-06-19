from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class RuntimeArtifactRef(BaseModel):
    artifact_name: str
    ref_id: str | None = None
    line: int | None = None
    path: str | None = None


class RuntimeEvidenceLink(BaseModel):
    evidence_id: str
    source_url: str | None = None
    page_title: str | None = None
    text_preview: str | None = None
    report_sections: list[str] = Field(default_factory=list)
    review_issue_ids: list[str] = Field(default_factory=list)
    raw: dict[str, Any] = Field(default_factory=dict)


class RuntimeTimelineItem(BaseModel):
    id: str
    timestamp: str | None = None
    kind: str
    category: str
    title: str
    summary: str | None = None
    status: str | None = None
    step_id: str | None = None
    tool_name: str | None = None
    evidence_ids: list[str] = Field(default_factory=list)
    artifact_refs: list[RuntimeArtifactRef] = Field(default_factory=list)
    raw_ref: RuntimeArtifactRef | None = None
    raw: dict[str, Any] = Field(default_factory=dict)


class RuntimeInspectorSummary(BaseModel):
    task_id: str
    status: str | None = None
    artifact_count: int = 0
    timeline_count: int = 0
    evidence_count: int = 0
    llm_call_count: int = 0
    real_llm_call_count: int = 0
    approval_count: int = 0
    recovery_count: int = 0
    review_status: str | None = None
    budget_decisions: dict[str, int] = Field(default_factory=dict)
    categories: dict[str, int] = Field(default_factory=dict)


class RuntimeStepDetail(BaseModel):
    item: RuntimeTimelineItem
    related_items: list[RuntimeTimelineItem] = Field(default_factory=list)
    evidence: list[RuntimeEvidenceLink] = Field(default_factory=list)


class RuntimeTimelineResponse(BaseModel):
    task_id: str
    summary: RuntimeInspectorSummary
    timeline_items: list[RuntimeTimelineItem] = Field(default_factory=list)


class RuntimeInspectorResponse(BaseModel):
    task_id: str
    status: str | None = None
    artifacts: list[str] = Field(default_factory=list)
    summary: RuntimeInspectorSummary
    timeline_items: list[RuntimeTimelineItem] = Field(default_factory=list)
    evidence_links: list[RuntimeEvidenceLink] = Field(default_factory=list)
    review_summary: dict[str, Any] = Field(default_factory=dict)
    llm_summary: dict[str, Any] = Field(default_factory=dict)
    approval_summary: dict[str, Any] = Field(default_factory=dict)
