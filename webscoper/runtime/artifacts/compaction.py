from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from webscoper.schemas.artifact import (
    CompactedBrowserState,
    CompactedEvidenceRef,
    CompactedRecoveryState,
    CompactedRiskState,
    CompactedStep,
    CompactionPolicy,
    CompactionResult,
    ContextPack,
)
from webscoper.schemas.artifact import EvidenceItem


class ContextCompactor:
    def __init__(self, policy: CompactionPolicy | None = None) -> None:
        self.policy = policy or CompactionPolicy()

    def should_compact(
        self,
        transcript_events: list[Any],
        trace_events: list[Any] | None = None,
        evidence_items: list[Any] | None = None,
    ) -> bool:
        trace_events = trace_events or []
        evidence_items = evidence_items or []
        return (
            len(transcript_events) > self.policy.max_transcript_events
            or len(trace_events) > self.policy.max_trace_events
            or len(evidence_items) > self.policy.max_evidence_items
        )

    def compact(
        self,
        *,
        task_id: str | None,
        task_goal: str | None,
        transcript_events: list[Any],
        trace_events: list[Any] | None = None,
        evidence_items: list[EvidenceItem] | None = None,
        recovery_attempts: list[Any] | None = None,
        approval_requests: list[Any] | None = None,
        risk_report: dict[str, Any] | None = None,
    ) -> CompactionResult:
        trace_events = trace_events or []
        evidence_items = evidence_items or []
        recovery_attempts = recovery_attempts or []
        approval_requests = approval_requests or []
        warnings: list[str] = []

        compacted = self.should_compact(
            transcript_events,
            trace_events,
            evidence_items,
        )
        current_state = _current_browser_state(trace_events, evidence_items, warnings)
        evidence_refs = [
            _compact_evidence_ref(item)
            for item in evidence_items[-self.policy.max_evidence_items :]
        ]
        recovery_state = _compact_recovery_state(recovery_attempts)
        risk_state = _compact_risk_state(approval_requests, risk_report)

        recent_events = transcript_events[-self.policy.preserve_recent_events :]
        older_events = transcript_events[: -self.policy.preserve_recent_events]
        recent_steps = [
            _compact_transcript_event(event, index, recent=True)
            for index, event in enumerate(recent_events, start=1)
        ]
        key_steps = _key_steps_from_events(
            older_events=older_events,
            trace_events=trace_events,
            recovery_attempts=recovery_attempts,
            policy=self.policy,
        )

        context_pack = ContextPack(
            task_id=task_id,
            task_goal=task_goal,
            current_state=current_state,
            key_steps=key_steps,
            recent_steps=recent_steps,
            evidence_refs=evidence_refs,
            recovery_state=recovery_state,
            risk_state=risk_state,
            open_questions=[],
            next_action_hint=_next_action_hint(current_state, recovery_state, risk_state),
            metadata={
                "policy": self.policy.model_dump(mode="json"),
                "compacted": compacted,
            },
        )
        before_counts = {
            "transcript_events": len(transcript_events),
            "trace_events": len(trace_events),
            "evidence_items": len(evidence_items),
            "recovery_attempts": len(recovery_attempts),
            "approval_requests": len(approval_requests),
        }
        after_counts = {
            "key_steps": len(context_pack.key_steps),
            "recent_steps": len(context_pack.recent_steps),
            "evidence_refs": len(context_pack.evidence_refs),
            "recent_recovery_attempts": len(
                context_pack.recovery_state.recent_attempts
                if context_pack.recovery_state is not None
                else []
            ),
        }
        return CompactionResult(
            compacted=compacted,
            reason=(
                "Compaction threshold exceeded."
                if compacted
                else "Compaction artifacts generated below threshold."
            ),
            before_counts=before_counts,
            after_counts=after_counts,
            context_pack=context_pack,
            warnings=warnings,
        )

    def write_artifacts(
        self,
        result: CompactionResult,
        output_dir: Path,
    ) -> None:
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "compact_context.json").write_text(
            json.dumps(result.model_dump(mode="json"), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        (output_dir / "compact_summary.md").write_text(
            build_compact_summary_markdown(result),
            encoding="utf-8",
        )


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    items: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            items.append(payload)
    return items


def load_evidence_jsonl(path: Path) -> list[EvidenceItem]:
    return [EvidenceItem.model_validate(item) for item in load_jsonl(path)]


def build_compact_summary_markdown(result: CompactionResult) -> str:
    pack = result.context_pack
    lines = [
        "# Compact Runtime Context",
        "",
        f"- compacted: {result.compacted}",
        f"- reason: {result.reason}",
        f"- task_id: {pack.task_id or 'none'}",
        f"- task_goal: {pack.task_goal or 'none'}",
        "",
        "## Current Browser State",
    ]
    if pack.current_state is None:
        lines.append("- unavailable")
    else:
        state = pack.current_state
        lines.extend(
            [
                f"- current_url: {state.current_url or 'none'}",
                f"- current_title: {state.current_title or 'none'}",
                f"- screenshot_path: {state.screenshot_path or 'none'}",
                f"- visible_text_preview: {state.visible_text_preview or 'none'}",
            ]
        )

    lines.extend(["", "## Key Steps"])
    lines.extend(_step_lines(pack.key_steps))
    lines.extend(["", "## Recent Steps"])
    lines.extend(_step_lines(pack.recent_steps))
    lines.extend(["", "## Evidence Refs"])
    if not pack.evidence_refs:
        lines.append("- none")
    for ref in pack.evidence_refs:
        lines.append(
            f"- {ref.evidence_id} ({ref.kind}) {ref.source_url or 'no-url'}: "
            f"{ref.text_preview or ''}"
        )

    lines.extend(["", "## Recovery State"])
    recovery = pack.recovery_state
    if recovery is None:
        lines.append("- none")
    else:
        lines.extend(
            [
                f"- total_attempts: {recovery.total_attempts}",
                f"- recovered_count: {recovery.recovered_count}",
                f"- failed_count: {recovery.failed_count}",
                f"- blocked_count: {recovery.blocked_count}",
            ]
        )

    lines.extend(["", "## Risk / Approval State"])
    risk = pack.risk_state
    if risk is None:
        lines.append("- none")
    else:
        lines.extend(
            [
                f"- has_pending_approval: {risk.has_pending_approval}",
                f"- pending_approval_ids: {', '.join(risk.pending_approval_ids) or 'none'}",
                f"- blocked: {risk.blocked}",
                f"- risk_signal_count: {len(risk.risk_signals)}",
            ]
        )

    if result.warnings:
        lines.extend(["", "## Warnings"])
        lines.extend(f"- {warning}" for warning in result.warnings)

    if pack.next_action_hint:
        lines.extend(["", "## Next Action Hint", "", pack.next_action_hint])
    return "\n".join(lines).rstrip() + "\n"


def _step_lines(steps: list[CompactedStep]) -> list[str]:
    if not steps:
        return ["- none"]
    return [
        f"- {step.step_id} [{step.kind}] {step.status or 'unknown'}: {step.summary}"
        for step in steps
    ]


def _current_browser_state(
    trace_events: list[Any],
    evidence_items: list[EvidenceItem],
    warnings: list[str],
) -> CompactedBrowserState | None:
    url_only_state: CompactedBrowserState | None = None
    for event in reversed(trace_events):
        payload = _to_dict(event)
        observation = payload.get("observation")
        if isinstance(observation, dict):
            visible_text = _str_or_none(observation.get("visible_text_summary"))
            if visible_text is not None or payload.get("url_after") is not None:
                state = CompactedBrowserState(
                    current_url=_str_or_none(
                        observation.get("url") or payload.get("url_after")
                    ),
                    current_title=_str_or_none(
                        observation.get("title") or payload.get("title")
                    ),
                    last_observation_summary=_preview(visible_text, 500),
                    visible_text_preview=_preview(visible_text, 300),
                    screenshot_path=_str_or_none(
                        observation.get("screenshot_path")
                        or payload.get("screenshot_path")
                    ),
                )
                if visible_text is not None:
                    return state
                url_only_state = url_only_state or state
        if payload.get("url_after") is not None:
            url_only_state = url_only_state or CompactedBrowserState(
                current_url=_str_or_none(payload.get("url_after")),
                current_title=_str_or_none(payload.get("title")),
                screenshot_path=_str_or_none(payload.get("screenshot_path")),
            )

    if url_only_state is not None:
        evidence_state = _browser_state_from_evidence(evidence_items)
        if (
            evidence_state is not None
            and evidence_state.current_url == url_only_state.current_url
        ):
            return evidence_state.model_copy(
                update={
                    "current_title": evidence_state.current_title
                    or url_only_state.current_title,
                    "screenshot_path": evidence_state.screenshot_path
                    or url_only_state.screenshot_path,
                }
            )
        return url_only_state

    evidence_state = _browser_state_from_evidence(evidence_items)
    if evidence_state is not None:
        return evidence_state

    warnings.append("Current browser state could not be inferred.")
    return None


def _browser_state_from_evidence(
    evidence_items: list[EvidenceItem],
) -> CompactedBrowserState | None:
    for item in reversed(evidence_items):
        if item.source_url or item.page_title or item.text or item.screenshot_path:
            return CompactedBrowserState(
                current_url=item.source_url,
                current_title=item.page_title,
                last_observation_summary=_preview(item.text, 500),
                visible_text_preview=_preview(item.text, 300),
                screenshot_path=item.screenshot_path,
            )
    return None


def _compact_evidence_ref(item: EvidenceItem) -> CompactedEvidenceRef:
    return CompactedEvidenceRef(
        evidence_id=item.evidence_id,
        kind=item.kind,
        source_url=item.source_url,
        page_title=item.page_title,
        text_preview=_preview(item.text, 300),
        screenshot_path=item.screenshot_path,
    )


def _compact_recovery_state(
    recovery_attempts: list[Any],
) -> CompactedRecoveryState:
    attempts = [_to_dict(attempt) for attempt in recovery_attempts]
    return CompactedRecoveryState(
        total_attempts=len(attempts),
        recovered_count=sum(1 for item in attempts if item.get("status") == "succeeded"),
        failed_count=sum(1 for item in attempts if item.get("status") == "failed"),
        blocked_count=sum(1 for item in attempts if item.get("status") == "blocked"),
        recent_attempts=attempts[-5:],
    )


def _compact_risk_state(
    approval_requests: list[Any],
    risk_report: dict[str, Any] | None,
) -> CompactedRiskState:
    approvals = [_to_dict(approval) for approval in approval_requests]
    pending_ids = [
        str(approval.get("approval_id"))
        for approval in approvals
        if approval.get("status") == "pending" and approval.get("approval_id")
    ]
    risk_report = risk_report or {}
    signals = risk_report.get("signals") if isinstance(risk_report, dict) else []
    return CompactedRiskState(
        has_pending_approval=bool(pending_ids),
        pending_approval_ids=pending_ids,
        blocked=bool(risk_report.get("blocked", 0)),
        risk_signals=signals if isinstance(signals, list) else [],
    )


def _key_steps_from_events(
    *,
    older_events: list[Any],
    trace_events: list[Any],
    recovery_attempts: list[Any],
    policy: CompactionPolicy,
) -> list[CompactedStep]:
    key_steps: list[CompactedStep] = []
    for index, event in enumerate(older_events, start=1):
        payload = _to_dict(event)
        kind = str(payload.get("event_type") or payload.get("kind") or "")
        if not _keep_transcript_event(kind, policy):
            continue
        key_steps.append(_compact_transcript_event(payload, index, recent=False))

    if policy.preserve_failed_steps:
        for index, event in enumerate(trace_events, start=1):
            payload = _to_dict(event)
            if payload.get("status") not in {"failed", "blocked"}:
                continue
            key_steps.append(_compact_trace_event(payload, index))

    if policy.preserve_recovery_steps:
        for index, attempt in enumerate(recovery_attempts, start=1):
            payload = _to_dict(attempt)
            key_steps.append(_compact_recovery_attempt(payload, index))

    deduped: list[CompactedStep] = []
    seen: set[tuple[str, str]] = set()
    for step in key_steps:
        key = (step.step_id, step.kind)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(step)
    return deduped


def _keep_transcript_event(kind: str, policy: CompactionPolicy) -> bool:
    if kind in {
        "task_loaded",
        "plan_built",
        "execution_failed",
        "execution_completed",
        "final_report_built",
        "review_completed",
    }:
        return True
    if policy.preserve_recovery_steps and kind.startswith("recovery_"):
        return True
    if policy.preserve_risk_events and "risk" in kind:
        return True
    if policy.preserve_approval_events and "approval" in kind:
        return True
    return False


def _compact_transcript_event(
    event: Any,
    index: int,
    recent: bool,
) -> CompactedStep:
    payload = _to_dict(event)
    event_type = str(payload.get("event_type") or payload.get("kind") or "event")
    body = _to_dict(payload.get("payload"))
    step_id = str(payload.get("event_id") or f"transcript_{index:06d}")
    return CompactedStep(
        step_id=step_id,
        source_event_ids=[step_id],
        kind=event_type,
        summary=_summarize_payload(event_type, body, recent=recent),
        evidence_ids=_extract_evidence_ids(body),
        source_urls=_extract_source_urls(body),
        status=_extract_status(body),
        metadata=_compact_metadata(body),
    )


def _compact_trace_event(event: dict[str, Any], index: int) -> CompactedStep:
    step_id = str(event.get("step_id") or f"trace_{index:06d}")
    action_type = str(event.get("action_type") or "trace_event")
    observation = _to_dict(event.get("observation"))
    summary = event.get("error_message") or _summarize_payload(action_type, observation)
    return CompactedStep(
        step_id=step_id,
        source_event_ids=[step_id],
        kind=action_type,
        summary=_preview(str(summary), 300) or action_type,
        evidence_ids=_extract_evidence_ids(observation),
        source_urls=_extract_source_urls(event) + _extract_source_urls(observation),
        status=_str_or_none(event.get("status")),
        metadata={
            "error_type": event.get("error_type"),
            "url_after": event.get("url_after"),
        },
    )


def _compact_recovery_attempt(
    attempt: dict[str, Any],
    index: int,
) -> CompactedStep:
    step_id = str(attempt.get("attempt_id") or f"recovery_{index:06d}")
    return CompactedStep(
        step_id=step_id,
        source_event_ids=[step_id],
        kind="recovery_attempt",
        summary=(
            f"{attempt.get('strategy', 'unknown')} ended as "
            f"{attempt.get('status', 'unknown')}: {attempt.get('reason', '')}"
        ).strip(),
        evidence_ids=[],
        source_urls=[
            url
            for url in [
                _str_or_none(attempt.get("before_url")),
                _str_or_none(attempt.get("after_url")),
            ]
            if url
        ],
        status=_str_or_none(attempt.get("status")),
        metadata={
            "error_type": attempt.get("error_type"),
            "strategy": attempt.get("strategy"),
        },
    )


def _summarize_payload(kind: str, payload: dict[str, Any], recent: bool = False) -> str:
    status = _extract_status(payload)
    url = _first_source_url(payload)
    pieces = [kind.replace("_", " ")]
    if status:
        pieces.append(f"status={status}")
    if url:
        pieces.append(f"url={url}")
    message = payload.get("message") or payload.get("error_message") or payload.get("error")
    if message:
        pieces.append(_preview(str(message), 180) or "")
    if recent:
        pieces.append("recent")
    return "; ".join(piece for piece in pieces if piece)


def _compact_metadata(payload: dict[str, Any]) -> dict[str, Any]:
    keep_keys = [
        "status",
        "error_type",
        "error_message",
        "run_id",
        "tool_id",
        "tool_name",
        "approval_id",
        "risk_level",
    ]
    return {key: payload.get(key) for key in keep_keys if key in payload}


def _extract_status(payload: dict[str, Any]) -> str | None:
    state = payload.get("state")
    if isinstance(state, dict) and state.get("status") is not None:
        return str(state.get("status"))
    if payload.get("status") is not None:
        return str(payload.get("status"))
    return None


def _extract_evidence_ids(payload: dict[str, Any]) -> list[str]:
    ids: list[str] = []

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            if value.get("evidence_id") is not None:
                ids.append(str(value["evidence_id"]))
            for item in value.values():
                visit(item)
        elif isinstance(value, list):
            for item in value:
                visit(item)

    visit(payload)
    return sorted(set(ids))


def _extract_source_urls(payload: dict[str, Any]) -> list[str]:
    urls: list[str] = []

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                if key in {"source_url", "url", "url_after", "target_url", "final_url"}:
                    text = _str_or_none(item)
                    if text:
                        urls.append(text)
                visit(item)
        elif isinstance(value, list):
            for item in value:
                visit(item)

    visit(payload)
    return sorted(set(urls))


def _first_source_url(payload: dict[str, Any]) -> str | None:
    urls = _extract_source_urls(payload)
    return urls[0] if urls else None


def _next_action_hint(
    current_state: CompactedBrowserState | None,
    recovery_state: CompactedRecoveryState,
    risk_state: CompactedRiskState,
) -> str | None:
    if risk_state.has_pending_approval:
        return "Wait for the pending approval decision before continuing."
    if risk_state.blocked:
        return "Do not continue blocked risky actions."
    if recovery_state.blocked_count > 0:
        return "A recent recovery attempt was blocked; avoid bypass behavior."
    if current_state and current_state.current_url:
        return "Continue from the current browser state while preserving evidence references."
    return None


def _to_dict(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    if hasattr(value, "model_dump"):
        dumped = value.model_dump(mode="json")
        return dumped if isinstance(dumped, dict) else {}
    return {}


def _preview(value: str | None, limit: int) -> str | None:
    if value is None:
        return None
    text = " ".join(str(value).split())
    if not text:
        return None
    return text if len(text) <= limit else text[:limit].rstrip()


def _str_or_none(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text if text else None
