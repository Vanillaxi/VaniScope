from __future__ import annotations

from collections import Counter
from typing import Any

from webscoper.runtime.inspector.links import (
    RuntimeArtifactLinker,
    evidence_ids_from_payload,
)
from webscoper.runtime.inspector.loader import RunArtifactLoader
from webscoper.runtime.inspector.presentation import artifact_presentations
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
        artifact_names = self.loader.list_artifacts()
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
            artifacts=artifact_names,
            summary=summary,
            timeline_items=items,
            evidence_links=linker.evidence_links(),
            task_summary=_task_summary(self.loader.task_id, status or self.status, summary),
            result_summary=_result_summary(
                status or self.status,
                artifacts["final_report"],
                artifacts["review"],
                artifacts["recovery"],
                artifacts["approvals"],
                artifacts["pending"],
            ),
            report_summary=_report_summary(artifacts["final_report"]),
            evidence_summary=_evidence_summary(artifacts["evidence"]),
            review_summary=_review_summary(artifacts["review"]),
            tool_summary=_tool_summary_rows(artifacts["tool_audit"]),
            llm_summary=_llm_summary(artifacts["llm_calls"], artifacts["prompt_context"]),
            recovery_summary=_recovery_summary(artifacts["recovery"]),
            approval_summary=_approval_summary(artifacts["approvals"], artifacts["pending"]),
            artifact_presentations=artifact_presentations(artifact_names),
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

        for record in artifacts["budget_decisions"]:
            order += 1
            candidates.append(
                (
                    _timestamp(record, "timestamp", "created_at"),
                    order,
                    _item_from_budget_decision(record, order),
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
        budget_decisions.update(
            str(item.get("decision"))
            for item in artifacts["budget_decisions"]
            if item.get("decision")
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
            "budget_decisions": self.loader.read_jsonl("budget_decisions.jsonl"),
            "recovery": self.loader.read_jsonl("recovery.jsonl"),
            "approvals": self.loader.read_jsonl("approvals.jsonl"),
            "pending": self.loader.read_jsonl("pending.jsonl"),
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
        duration_ms=_duration_ms(payload),
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
        duration_ms=_duration_ms(record) or record.get("latency_ms"),
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
        duration_ms=_duration_ms(record),
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
        duration_ms=_duration_ms(record),
        evidence_ids=evidence_ids_from_payload(record),
        artifact_refs=[_ref("llm_calls.jsonl", record)],
        raw_ref=_ref("llm_calls.jsonl", record),
        raw=record,
    )


def _item_from_budget_decision(record: dict[str, Any], order: int) -> RuntimeTimelineItem:
    decision = str(record.get("decision") or "budget_checked")
    return RuntimeTimelineItem(
        id=_id("budget", record, order, preferred=f"{decision}_{order}"),
        timestamp=_timestamp(record, "timestamp", "created_at"),
        kind="budget_decision",
        category="budget",
        title=f"Budget: {_title_from_kind(decision)}",
        summary=(
            f"{record.get('estimated_prompt_tokens')} prompt tokens; "
            f"approval threshold {record.get('approval_threshold')}"
        ),
        status=decision,
        duration_ms=_duration_ms(record),
        evidence_ids=evidence_ids_from_payload(record),
        artifact_refs=[_ref("budget_decisions.jsonl", record)],
        raw_ref=_ref("budget_decisions.jsonl", record),
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
        duration_ms=_duration_ms(record),
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
        duration_ms=_duration_ms(record),
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
        duration_ms=_duration_ms(record),
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
    if kind.startswith("workflow_") or kind in {"task_started", "task_finished", "task_failed", "task_canceled"}:
        return "workflow"
    if kind.startswith("budget_"):
        return "budget"
    if kind.startswith("user_") or kind in {"task_paused", "task_resumed"}:
        return "control"
    if (
        kind.startswith("browser_")
        or kind.startswith("navigation_")
        or kind.startswith("action_")
        or kind.startswith("post_action_")
        or kind.startswith("executor_")
    ):
        return "browser"
    if kind.startswith("readiness_") or kind == "readiness_check":
        return "readiness"
    if kind.startswith("effect_verification") or kind.startswith("verifier_"):
        return "verification"
    if kind.startswith("tool_"):
        return "tool"
    if kind.startswith("llm_") or kind in {"planner_started", "planner_finished"}:
        return "llm"
    if kind.startswith("recovery_"):
        return "recovery"
    if "approval" in kind:
        return "approval"
    if "evidence" in kind:
        return "evidence"
    if "review" in kind or "revision" in kind or "revise" in kind:
        return "review"
    if "report" in kind:
        return "report"
    if "failed" in kind or "error" in kind or "timeout" in kind:
        return "error"
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
        return {"available": False, "passed": None, "score": None}
    issues = review.get("issues") if isinstance(review.get("issues"), list) else []
    unsupported = _unsupported_claims(review)
    return {
        "available": True,
        "passed": review.get("passed") if isinstance(review.get("passed"), bool) else None,
        "status": _review_status(review),
        "score": review.get("score"),
        "issue_count": len(issues),
        "unsupported_claim_count": len(unsupported),
        "issues": issues,
        "unsupported_claims": unsupported,
        "recommendation": _string_or_none(review.get("summary")),
        "summary": _string_or_none(review.get("summary")),
    }


def _llm_summary(llm_calls: list[dict[str, Any]], prompt_context: dict[str, Any]) -> dict[str, Any]:
    budget_decisions = Counter(
        str(call.get("budget_decision"))
        for call in llm_calls
        if call.get("budget_decision")
    )
    modes = sorted(set(str(call.get("mode")) for call in llm_calls if call.get("mode")))
    providers = sorted(set(str(call.get("provider")) for call in llm_calls if call.get("provider")))
    models = sorted(set(str(call.get("model")) for call in llm_calls if call.get("model")))
    prompt_tokens = sum(_int_value(call.get("prompt_tokens_estimated")) for call in llm_calls)
    completion_tokens = sum(
        _int_value(call.get("completion_tokens_estimated")) for call in llm_calls
    )
    real_call_count = sum(
        1
        for call in llm_calls
        if str(call.get("mode") or "").lower() in {"real", "openai_compatible", "real_llm"}
    )
    return {
        "call_count": len(llm_calls),
        "real_call_count": real_call_count,
        "real_llm_used": real_call_count > 0,
        "modes": modes,
        "mode": ", ".join(modes) if modes else "deterministic",
        "providers": providers,
        "provider": ", ".join(providers) if providers else "none",
        "models": models,
        "model": ", ".join(models) if models else None,
        "estimated_tokens": prompt_tokens + completion_tokens,
        "prompt_tokens_estimated": prompt_tokens,
        "completion_tokens_estimated": completion_tokens,
        "budget_decisions": dict(budget_decisions),
        "has_prompt_context": bool(prompt_context),
        "prompt_skill_id": _prompt_skill_id(prompt_context),
    }


def _approval_summary(
    approvals: list[dict[str, Any]],
    pending: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    statuses = Counter(str(item.get("status")) for item in approvals if item.get("status"))
    pending_count = statuses.get("pending", 0) + len(pending or [])
    return {
        "count": len(approvals),
        "statuses": dict(statuses),
        "pending_count": pending_count,
        "approved_count": statuses.get("approved", 0),
        "rejected_count": statuses.get("rejected", 0),
        "blocked_count": statuses.get("blocked", 0),
    }


def _task_summary(
    task_id: str,
    status: str | None,
    summary: RuntimeInspectorSummary,
) -> dict[str, Any]:
    return {
        "task_id": task_id,
        "status": status,
        "artifact_count": summary.artifact_count,
        "timeline_count": summary.timeline_count,
        "categories": summary.categories,
    }


def _result_summary(
    status: str | None,
    final_report: str,
    review: dict[str, Any],
    recovery: list[dict[str, Any]],
    approvals: list[dict[str, Any]],
    pending: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "status": status,
        "has_report": bool(final_report.strip()),
        "review_status": _review_status(review),
        "review_passed": review.get("passed") if isinstance(review.get("passed"), bool) else None,
        "recovery_attempts": len(recovery),
        "approval_count": len(approvals),
        "pending_approval_count": len(pending)
        + sum(1 for item in approvals if item.get("status") == "pending"),
    }


def _report_summary(report_text: str) -> dict[str, Any]:
    if not report_text.strip():
        return {"available": False, "title": None, "summary": None, "sections": [], "source_urls": []}
    lines = report_text.splitlines()
    title = None
    sections: list[str] = []
    paragraphs: list[str] = []
    current: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("#"):
            heading = stripped.lstrip("#").strip()
            if heading:
                sections.append(heading)
                if title is None:
                    title = heading
            continue
        if not stripped:
            if current:
                paragraphs.append(" ".join(current))
                current = []
            continue
        if not stripped.startswith(("```", "-", "*", "|")):
            current.append(stripped)
    if current:
        paragraphs.append(" ".join(current))
    return {
        "available": True,
        "title": title or "Final report",
        "summary": _preview(paragraphs[0] if paragraphs else report_text, 480),
        "sections": sections,
        "source_urls": _source_urls(report_text),
    }


def _evidence_summary(evidence: list[dict[str, Any]]) -> dict[str, Any]:
    source_urls = sorted(
        {str(item.get("source_url")) for item in evidence if item.get("source_url")}
    )
    page_titles = sorted(
        {str(item.get("page_title")) for item in evidence if item.get("page_title")}
    )
    evidence_ids = [
        str(item.get("evidence_id")) for item in evidence if item.get("evidence_id")
    ]
    return {
        "count": len(evidence),
        "total_count": len(evidence),
        "source_urls": source_urls,
        "page_titles": page_titles,
        "evidence_ids": evidence_ids,
        "top_snippets": [
            {
                "evidence_id": item.get("evidence_id"),
                "source_url": item.get("source_url"),
                "page_title": item.get("page_title"),
                "text_preview": _preview(item.get("text"), 220),
            }
            for item in evidence[:5]
        ],
    }


def _tool_summary_rows(tool_audit: list[dict[str, Any]]) -> dict[str, Any]:
    tools = Counter(str(item.get("tool_name")) for item in tool_audit if item.get("tool_name"))
    statuses = Counter(str(item.get("status")) for item in tool_audit if item.get("status"))
    decisions = Counter(str(item.get("decision")) for item in tool_audit if item.get("decision"))
    return {
        "total_calls": len(tool_audit),
        "tools_used": dict(tools),
        "failed_calls": sum(
            1
            for item in tool_audit
            if str(item.get("status") or "").lower() in {"failed", "error"}
            or bool(item.get("error_type"))
        ),
        "blocked_calls": decisions.get("blocked", 0) + statuses.get("blocked", 0),
        "approval_required_calls": decisions.get("approval_required", 0),
        "statuses": dict(statuses),
        "decisions": dict(decisions),
    }


def _recovery_summary(recovery: list[dict[str, Any]]) -> dict[str, Any]:
    kinds = Counter(
        str(item.get("kind") or item.get("event_type"))
        for item in recovery
        if item.get("kind") or item.get("event_type")
    )
    statuses = Counter(
        str(item.get("status") or item.get("outcome"))
        for item in recovery
        if item.get("status") or item.get("outcome")
    )
    return {
        "attempt_count": len(recovery),
        "recovery_attempts": len(recovery),
        "recovery_kinds": dict(kinds),
        "success_count": statuses.get("success", 0) + statuses.get("succeeded", 0),
        "failed_count": statuses.get("failed", 0) + statuses.get("error", 0),
        "statuses": dict(statuses),
    }


def _unsupported_claims(review: dict[str, Any]) -> list[Any]:
    direct = review.get("unsupported_claims")
    if isinstance(direct, list):
        return direct
    claim_checks = review.get("claim_checks")
    if not isinstance(claim_checks, list):
        return []
    return [
        check
        for check in claim_checks
        if isinstance(check, dict) and check.get("supported") is False
    ]


def _source_urls(value: str) -> list[str]:
    urls: list[str] = []
    for raw in value.replace(")", " ").replace("]", " ").split():
        token = raw.strip(".,;:")
        if token.startswith(("http://", "https://", "file://")) and token not in urls:
            urls.append(token)
    return urls[:20]


def _prompt_skill_id(prompt_context: dict[str, Any]) -> str | None:
    skill = prompt_context.get("skill") if isinstance(prompt_context, dict) else None
    if isinstance(skill, dict) and isinstance(skill.get("skill_id"), str):
        return skill["skill_id"]
    return None


def _string_or_none(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _int_value(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return 0


def _duration_ms(record: dict[str, Any]) -> int | float | None:
    for key in ("duration_ms", "latency_ms", "elapsed_ms"):
        value = record.get(key)
        if isinstance(value, bool):
            continue
        if isinstance(value, (int, float)):
            return value
    return None


def _preview(value: Any, limit: int = 240) -> str | None:
    if value is None:
        return None
    compact = " ".join(str(value).split())
    if not compact:
        return None
    return compact if len(compact) <= limit else compact[: limit - 1] + "…"


def _slug(value: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in value).strip("_") or "item"
