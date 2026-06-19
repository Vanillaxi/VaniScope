from __future__ import annotations

from collections import Counter
from typing import Any

from webscoper.runtime.inspector.links import (
    RuntimeArtifactLinker,
    evidence_ids_from_payload,
)
from webscoper.runtime.inspector.loader import RunArtifactLoader
from webscoper.runtime.inspector.schemas import (
    RuntimeArtifactRef,
    RuntimeInspectorResponse,
    RuntimeInspectorSummary,
    RuntimeTimelineItem,
    RuntimeTimelineResponse,
)


class RuntimeTimelineBuilder:
    def __init__(self, loader: RunArtifactLoader, status: str | None = None) -> None:
        self.loader = loader
        self.status = status

    def build_timeline_response(self) -> RuntimeTimelineResponse:
        artifacts = self._load_artifacts()
        items = self.build_items(artifacts)
        summary = self.build_summary(artifacts, items)
        return RuntimeTimelineResponse(
            task_id=self.loader.task_id,
            summary=summary,
            timeline_items=items,
        )

    def build_inspector_response(self, status: str | None = None) -> RuntimeInspectorResponse:
        artifacts = self._load_artifacts()
        items = self.build_items(artifacts)
        summary = self.build_summary(artifacts, items, status=status or self.status)
        linker = RuntimeArtifactLinker(
            evidence=artifacts["evidence"],
            final_report=artifacts["final_report"],
            review=artifacts["review"],
            tool_audit=artifacts["tool_audit"],
            llm_calls=artifacts["llm_calls"],
            trace=artifacts["trace"],
            approvals=artifacts["approvals"],
        )
        return RuntimeInspectorResponse(
            task_id=self.loader.task_id,
            status=status or self.status,
            artifacts=self.loader.list_artifacts(),
            summary=summary,
            timeline_items=items,
            evidence_links=linker.evidence_links(),
            review_summary=_review_summary(artifacts["review"]),
            llm_summary=_llm_summary(artifacts["llm_calls"], artifacts["prompt_context"]),
            approval_summary=_approval_summary(artifacts["approvals"]),
        )

    def build_items(self, artifacts: dict[str, Any]) -> list[RuntimeTimelineItem]:
        candidates: list[tuple[str | None, int, RuntimeTimelineItem]] = []
        order = 0

        for record in artifacts["events"]:
            order += 1
            candidates.append(
                (
                    _timestamp(record, "created_at", "timestamp"),
                    order,
                    _item_from_event(record, order),
                )
            )

        for record in artifacts["trace"]:
            order += 1
            candidates.append(
                (
                    _timestamp(record, "created_at", "timestamp"),
                    order,
                    _item_from_trace(record, order),
                )
            )

        for record in artifacts["tool_audit"]:
            order += 1
            candidates.append(
                (
                    _timestamp(record, "timestamp", "created_at"),
                    order,
                    _item_from_tool_audit(record, order),
                )
            )

        for record in artifacts["llm_calls"]:
            order += 1
            candidates.append(
                (
                    _timestamp(record, "timestamp", "created_at"),
                    order,
                    _item_from_llm_call(record, order),
                )
            )

        for record in artifacts["recovery"]:
            order += 1
            candidates.append(
                (
                    _timestamp(record, "timestamp", "created_at"),
                    order,
                    _item_from_recovery(record, order),
                )
            )

        for record in artifacts["approvals"]:
            order += 1
            candidates.append(
                (
                    _timestamp(record, "created_at", "decided_at", "timestamp"),
                    order,
                    _item_from_approval(record, order),
                )
            )

        for record in artifacts["evidence"]:
            order += 1
            candidates.append(
                (
                    _timestamp(record, "created_at", "timestamp"),
                    order,
                    _item_from_evidence(record, order),
                )
            )

        if artifacts["review"]:
            order += 1
            candidates.append((None, order, _item_from_review(artifacts["review"], order)))

        if artifacts["final_report"]:
            order += 1
            candidates.append((None, order, _item_from_report(artifacts["final_report"], order)))

        candidates.sort(key=lambda item: (item[0] is None, item[0] or "", item[1]))
        return [item for _, _, item in candidates]

    def build_summary(
        self,
        artifacts: dict[str, Any],
        items: list[RuntimeTimelineItem],
        status: str | None = None,
    ) -> RuntimeInspectorSummary:
        categories = Counter(item.category for item in items)
        budget_decisions = Counter(
            str(call.get("budget_decision"))
            for call in artifacts["llm_calls"]
            if call.get("budget_decision")
        )
        real_llm_calls = sum(
            1
            for call in artifacts["llm_calls"]
            if str(call.get("mode") or "").lower() in {"real", "openai_compatible"}
        )
        return RuntimeInspectorSummary(
            task_id=self.loader.task_id,
            status=status or self.status,
            artifact_count=len(self.loader.list_artifacts()),
            timeline_count=len(items),
            evidence_count=len(artifacts["evidence"]),
            llm_call_count=len(artifacts["llm_calls"]),
            real_llm_call_count=real_llm_calls,
            approval_count=len(artifacts["approvals"]),
            recovery_count=len(artifacts["recovery"]),
            review_status=_review_status(artifacts["review"]),
            budget_decisions=dict(budget_decisions),
            categories=dict(categories),
        )

    def _load_artifacts(self) -> dict[str, Any]:
        return {
            "events": self.loader.read_jsonl("events.jsonl"),
            "trace": self.loader.read_jsonl("trace.jsonl"),
            "tool_audit": self.loader.read_jsonl("tool_audit.jsonl"),
            "llm_calls": self.loader.read_jsonl("llm_calls.jsonl"),
            "recovery": self.loader.read_jsonl("recovery.jsonl"),
            "approvals": self.loader.read_jsonl("approvals.jsonl"),
            "evidence": self.loader.read_jsonl("evidence.jsonl"),
            "review": self.loader.read_json("review.json"),
            "prompt_context": self.loader.read_json("prompt_context.json"),
            "final_report": self.loader.read_text("final_report.md"),
        }


def _item_from_event(record: dict[str, Any], order: int) -> RuntimeTimelineItem:
    kind = str(record.get("kind") or record.get("event") or "event")
    payload = record.get("payload") if isinstance(record.get("payload"), dict) else {}
    return RuntimeTimelineItem(
        id=_id("event", record, order),
        timestamp=_timestamp(record, "created_at", "timestamp"),
        kind=kind,
        category=_event_category(kind),
        title=_title_from_kind(kind),
        summary=_string_or_none(record.get("message")) or _summary_from_payload(payload),
        status=_status_from_record(record, payload),
        step_id=_string_or_none(payload.get("step_id") or payload.get("step")),
        tool_name=_string_or_none(payload.get("tool_name") or payload.get("tool_id")),
        evidence_ids=evidence_ids_from_payload(record),
        artifact_refs=[_ref("events.jsonl", record)],
        raw_ref=_ref("events.jsonl", record),
        raw=record,
    )


def _item_from_trace(record: dict[str, Any], order: int) -> RuntimeTimelineItem:
    action_type = str(record.get("action_type") or "trace_step")
    step_id = _string_or_none(record.get("step_id"))
    return RuntimeTimelineItem(
        id=_id("trace", record, order, preferred=step_id),
        timestamp=_timestamp(record, "created_at", "timestamp"),
        kind=action_type,
        category="browser",
        title=_title_from_kind(action_type),
        summary=_trace_summary(record),
        status=_string_or_none(record.get("status")),
        step_id=step_id,
        tool_name=action_type,
        evidence_ids=evidence_ids_from_payload(record),
        artifact_refs=[_ref("trace.jsonl", record)],
        raw_ref=_ref("trace.jsonl", record),
        raw=record,
    )


def _item_from_tool_audit(record: dict[str, Any], order: int) -> RuntimeTimelineItem:
    tool_name = str(record.get("tool_name") or "tool")
    return RuntimeTimelineItem(
        id=_id("tool", record, order, preferred=tool_name),
        timestamp=_timestamp(record, "timestamp", "created_at"),
        kind="tool_audit",
        category="tool",
        title=f"Tool audit: {tool_name}",
        summary=_tool_summary(record),
        status=_string_or_none(record.get("status") or record.get("decision")),
        tool_name=tool_name,
        evidence_ids=evidence_ids_from_payload(record),
        artifact_refs=[_ref("tool_audit.jsonl", record)],
        raw_ref=_ref("tool_audit.jsonl", record),
        raw=record,
    )


def _item_from_llm_call(record: dict[str, Any], order: int) -> RuntimeTimelineItem:
    purpose = str(record.get("purpose") or "llm")
    provider = str(record.get("provider") or "provider")
    return RuntimeTimelineItem(
        id=_id("llm", record, order),
        timestamp=_timestamp(record, "timestamp", "created_at"),
        kind="llm_call",
        category="llm",
        title=f"LLM call: {purpose}",
        summary=(
            f"{provider} / {record.get('model') or 'model'} "
            f"({record.get('budget_decision') or 'budget unknown'})"
        ),
        status=_string_or_none(record.get("status")),
        evidence_ids=evidence_ids_from_payload(record),
        artifact_refs=[_ref("llm_calls.jsonl", record)],
        raw_ref=_ref("llm_calls.jsonl", record),
        raw=record,
    )


def _item_from_recovery(record: dict[str, Any], order: int) -> RuntimeTimelineItem:
    kind = str(record.get("kind") or record.get("event_type") or "recovery")
    return RuntimeTimelineItem(
        id=_id("recovery", record, order),
        timestamp=_timestamp(record, "timestamp", "created_at"),
        kind=kind,
        category="recovery",
        title=_title_from_kind(kind),
        summary=_summary_from_payload(record),
        status=_string_or_none(record.get("status") or record.get("outcome")),
        step_id=_string_or_none(record.get("step_id") or record.get("failed_step_id")),
        tool_name=_string_or_none(record.get("tool_name") or record.get("action_type")),
        evidence_ids=evidence_ids_from_payload(record),
        artifact_refs=[_ref("recovery.jsonl", record)],
        raw_ref=_ref("recovery.jsonl", record),
        raw=record,
    )


def _item_from_approval(record: dict[str, Any], order: int) -> RuntimeTimelineItem:
    approval_id = _string_or_none(record.get("approval_id"))
    return RuntimeTimelineItem(
        id=_id("approval", record, order, preferred=approval_id),
        timestamp=_timestamp(record, "created_at", "decided_at", "timestamp"),
        kind="approval",
        category="approval",
        title=f"Approval: {record.get('status') or 'pending'}",
        summary=_string_or_none(record.get("reason")) or _summary_from_payload(record),
        status=_string_or_none(record.get("status")),
        tool_name=_string_or_none(record.get("tool_name")),
        evidence_ids=evidence_ids_from_payload(record),
        artifact_refs=[_ref("approvals.jsonl", record)],
        raw_ref=_ref("approvals.jsonl", record),
        raw=record,
    )


def _item_from_evidence(record: dict[str, Any], order: int) -> RuntimeTimelineItem:
    evidence_id = _string_or_none(record.get("evidence_id"))
    return RuntimeTimelineItem(
        id=_id("evidence", record, order, preferred=evidence_id),
        timestamp=_timestamp(record, "created_at", "timestamp"),
        kind=str(record.get("kind") or "evidence"),
        category="evidence",
        title=f"Evidence collected: {evidence_id or order}",
        summary=_preview(record.get("text")) or _string_or_none(record.get("source_url")),
        status="collected",
        step_id=_string_or_none(record.get("trace_event_id")),
        evidence_ids=[evidence_id] if evidence_id else [],
        artifact_refs=[_ref("evidence.jsonl", record)],
        raw_ref=_ref("evidence.jsonl", record),
        raw=record,
    )


def _item_from_review(record: dict[str, Any], order: int) -> RuntimeTimelineItem:
    return RuntimeTimelineItem(
        id=f"review_{order:06d}",
        kind="review",
        category="review",
        title="Review finished",
        summary=_review_status(record) or "Review artifact generated.",
        status=_review_status(record),
        evidence_ids=evidence_ids_from_payload(record),
        artifact_refs=[RuntimeArtifactRef(artifact_name="review.json")],
        raw_ref=RuntimeArtifactRef(artifact_name="review.json"),
        raw=record,
    )


def _item_from_report(report_text: str, order: int) -> RuntimeTimelineItem:
    return RuntimeTimelineItem(
        id=f"report_{order:06d}",
        kind="report",
        category="report",
        title="Report generated",
        summary=_preview(report_text, 320),
        status="generated",
        evidence_ids=evidence_ids_from_payload(report_text),
        artifact_refs=[RuntimeArtifactRef(artifact_name="final_report.md")],
        raw_ref=RuntimeArtifactRef(artifact_name="final_report.md"),
        raw={},
    )


def _event_category(kind: str) -> str:
    if kind.startswith("workflow_") or kind in {"task_started", "task_finished", "task_failed"}:
        return "workflow"
    if kind.startswith("tool_"):
        return "tool"
    if kind.startswith("llm_") or kind in {"planner_started", "planner_finished"}:
        return "llm"
    if kind.startswith("recovery_"):
        return "recovery"
    if "approval" in kind or kind in {"task_paused", "task_resumed"}:
        return "approval"
    if "evidence" in kind:
        return "evidence"
    if "review" in kind or "revision" in kind or "revise" in kind:
        return "review"
    if "report" in kind:
        return "report"
    return "workflow"


def _timestamp(record: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = record.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def _id(prefix: str, record: dict[str, Any], order: int, preferred: str | None = None) -> str:
    if preferred:
        return f"{prefix}_{_slug(preferred)}"
    for key in ("event_id", "approval_id", "evidence_id", "step_id", "call_id"):
        value = record.get(key)
        if isinstance(value, str) and value:
            return f"{prefix}_{_slug(value)}"
    return f"{prefix}_{order:06d}"


def _ref(artifact_name: str, record: dict[str, Any]) -> RuntimeArtifactRef:
    line = record.get("_line")
    return RuntimeArtifactRef(
        artifact_name=artifact_name,
        ref_id=_string_or_none(
            record.get("event_id")
            or record.get("step_id")
            or record.get("approval_id")
            or record.get("evidence_id")
        ),
        line=line if isinstance(line, int) else None,
    )


def _title_from_kind(kind: str) -> str:
    return kind.replace("_", " ").strip().capitalize()


def _summary_from_payload(payload: Any) -> str | None:
    if not isinstance(payload, dict):
        return _preview(payload)
    for key in ("summary", "message", "error", "error_message", "reason", "phase"):
        value = payload.get(key)
        if isinstance(value, str) and value:
            return value
    return _preview(payload)


def _status_from_record(record: dict[str, Any], payload: dict[str, Any]) -> str | None:
    return _string_or_none(record.get("status")) or _string_or_none(payload.get("status"))


def _trace_summary(record: dict[str, Any]) -> str | None:
    if record.get("error_message"):
        return _string_or_none(record.get("error_message"))
    before = record.get("url_before")
    after = record.get("url_after")
    title = record.get("title")
    parts = [str(part) for part in (title, before, after) if isinstance(part, str) and part]
    return " -> ".join(parts) if parts else _summary_from_payload(record)


def _tool_summary(record: dict[str, Any]) -> str:
    decision = record.get("decision") or "decision unknown"
    risk = record.get("risk_level") or "risk unknown"
    duration = record.get("duration_ms")
    suffix = f", {duration}ms" if duration is not None else ""
    return f"{decision} / {risk}{suffix}"


def _review_status(review: dict[str, Any]) -> str | None:
    if not review:
        return None
    for key in ("status", "result"):
        value = review.get(key)
        if isinstance(value, str) and value:
            return value
    passed = review.get("passed")
    if isinstance(passed, bool):
        return "passed" if passed else "failed"
    return None


def _review_summary(review: dict[str, Any]) -> dict[str, Any]:
    if not review:
        return {"available": False}
    issues = review.get("issues") if isinstance(review.get("issues"), list) else []
    unsupported = (
        review.get("unsupported_claims")
        if isinstance(review.get("unsupported_claims"), list)
        else []
    )
    return {
        "available": True,
        "status": _review_status(review),
        "score": review.get("score"),
        "issue_count": len(issues),
        "unsupported_claim_count": len(unsupported),
        "issues": issues,
        "unsupported_claims": unsupported,
    }


def _llm_summary(llm_calls: list[dict[str, Any]], prompt_context: dict[str, Any]) -> dict[str, Any]:
    budget_decisions = Counter(
        str(call.get("budget_decision"))
        for call in llm_calls
        if call.get("budget_decision")
    )
    modes = sorted(set(str(call.get("mode")) for call in llm_calls if call.get("mode")))
    providers = sorted(set(str(call.get("provider")) for call in llm_calls if call.get("provider")))
    return {
        "call_count": len(llm_calls),
        "real_call_count": sum(
            1
            for call in llm_calls
            if str(call.get("mode") or "").lower() in {"real", "openai_compatible"}
        ),
        "modes": modes,
        "providers": providers,
        "budget_decisions": dict(budget_decisions),
        "has_prompt_context": bool(prompt_context),
        "prompt_skill_id": _prompt_skill_id(prompt_context),
    }


def _approval_summary(approvals: list[dict[str, Any]]) -> dict[str, Any]:
    statuses = Counter(str(item.get("status")) for item in approvals if item.get("status"))
    return {
        "count": len(approvals),
        "statuses": dict(statuses),
        "pending_count": statuses.get("pending", 0),
    }


def _prompt_skill_id(prompt_context: dict[str, Any]) -> str | None:
    skill = prompt_context.get("skill") if isinstance(prompt_context, dict) else None
    if isinstance(skill, dict) and isinstance(skill.get("skill_id"), str):
        return skill["skill_id"]
    return None


def _string_or_none(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _preview(value: Any, limit: int = 240) -> str | None:
    if value is None:
        return None
    compact = " ".join(str(value).split())
    if not compact:
        return None
    return compact if len(compact) <= limit else compact[: limit - 1] + "…"


def _slug(value: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in value).strip("_") or "item"
