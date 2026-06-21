from __future__ import annotations

import json
from typing import Any

from webscoper.runtime.inspector.loader import RunArtifactLoader
from webscoper.runtime.inspector.schemas import (
    RuntimeExecutionGraphResponse,
    RuntimeGraphEdge,
    RuntimeGraphNode,
)


class RuntimeGraphBuilder:
    def __init__(self, loader: RunArtifactLoader, status: str | None = None) -> None:
        self.loader = loader
        self.status = status

    def build_graph_response(self, *, persist: bool = False) -> RuntimeExecutionGraphResponse:
        try:
            response = self._build()
        except Exception as exc:
            response = self._fallback(str(exc))
        if persist:
            self.write_graph_json(response)
        return response

    def write_graph_json(self, graph: RuntimeExecutionGraphResponse) -> None:
        try:
            self.loader.run_dir.mkdir(parents=True, exist_ok=True)
            (self.loader.run_dir / "graph.json").write_text(
                json.dumps(graph.model_dump(mode="json"), indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception:
            return

    def _build(self) -> RuntimeExecutionGraphResponse:
        artifacts = _load_artifacts(self.loader)
        rows: list[tuple[str | None, int, RuntimeGraphNode]] = []
        order = 0

        for record in artifacts["events"]:
            order += 1
            rows.append((_timestamp(record, "created_at", "timestamp"), order, _event_node(record, order)))

        for record in artifacts["llm_calls"]:
            order += 1
            rows.append((_timestamp(record, "timestamp", "created_at"), order, _llm_node(record, order)))

        for record in artifacts["tool_audit"]:
            order += 1
            rows.append((_timestamp(record, "timestamp", "created_at"), order, _tool_node(record, order)))

        for record in artifacts["trace"]:
            order += 1
            rows.append((_timestamp(record, "created_at", "timestamp"), order, _trace_node(record, order)))

        for record in artifacts["approvals"]:
            order += 1
            rows.append((_timestamp(record, "created_at", "decided_at", "timestamp"), order, _approval_node(record, order)))

        for record in artifacts["recovery"]:
            order += 1
            rows.append((_timestamp(record, "timestamp", "created_at"), order, _recovery_node(record, order)))

        for record in artifacts["evidence"]:
            order += 1
            rows.append((_timestamp(record, "created_at", "timestamp"), order, _evidence_node(record, order)))

        if artifacts["final_report"].strip():
            order += 1
            rows.append((None, order, _report_node(artifacts["final_report"], order)))

        rows.sort(key=lambda item: (item[0] is None, item[0] or "", item[1]))
        nodes = _dedupe_nodes([node for _, _, node in rows])
        edges = _sequence_edges(nodes)
        edges.extend(_evidence_edges(nodes))

        if not nodes:
            nodes = [
                RuntimeGraphNode(
                    id="task_empty",
                    type="task",
                    label="Task",
                    status=self.status or "unknown",
                    summary="No runtime artifacts were available.",
                    metadata={"task_id": self.loader.task_id},
                )
            ]

        return RuntimeExecutionGraphResponse(
            task_id=self.loader.task_id,
            nodes=nodes,
            edges=_dedupe_edges(edges),
        )

    def _fallback(self, error: str) -> RuntimeExecutionGraphResponse:
        return RuntimeExecutionGraphResponse(
            task_id=self.loader.task_id,
            fallback=True,
            error=error,
            nodes=[
                RuntimeGraphNode(
                    id="graph_fallback",
                    type="error",
                    label="Graph unavailable",
                    status="failed",
                    summary=error,
                    metadata={"task_id": self.loader.task_id},
                )
            ],
            edges=[],
        )


def _load_artifacts(loader: RunArtifactLoader) -> dict[str, Any]:
    return {
        "events": loader.read_jsonl("events.jsonl"),
        "trace": loader.read_jsonl("trace.jsonl"),
        "tool_audit": loader.read_jsonl("tool_audit.jsonl"),
        "llm_calls": loader.read_jsonl("llm_calls.jsonl"),
        "recovery": loader.read_jsonl("recovery.jsonl"),
        "approvals": loader.read_jsonl("approvals.jsonl"),
        "evidence": loader.read_jsonl("evidence.jsonl"),
        "final_report": loader.read_text("final_report.md"),
    }


def _event_node(record: dict[str, Any], order: int) -> RuntimeGraphNode:
    kind = str(record.get("kind") or record.get("event") or "event")
    payload = record.get("payload") if isinstance(record.get("payload"), dict) else {}
    return RuntimeGraphNode(
        id=_node_id("event", record, order),
        type=_node_type_for_kind(kind),
        label=_label_for_kind(kind, payload),
        status=_status_for_event(kind, payload),
        timestamp=_timestamp(record, "created_at", "timestamp"),
        duration_ms=_duration_ms(payload),
        summary=_summary(payload) or _string(record.get("message")),
        metadata={
            "source": "events.jsonl",
            "kind": kind,
            "event_id": record.get("event_id"),
            "payload": payload,
            "evidence_ids": _evidence_ids(record),
        },
    )


def _llm_node(record: dict[str, Any], order: int) -> RuntimeGraphNode:
    purpose = str(record.get("purpose") or "llm")
    provider = _string(record.get("provider")) or "provider"
    model = _string(record.get("model")) or "model"
    return RuntimeGraphNode(
        id=_node_id("llm", record, order),
        type="llm",
        label=f"LLM: {purpose}",
        status=_string(record.get("status")) or "success",
        timestamp=_timestamp(record, "timestamp", "created_at"),
        duration_ms=_duration_ms(record),
        summary=f"{provider} / {model}",
        metadata={"source": "llm_calls.jsonl", "raw": record},
    )


def _tool_node(record: dict[str, Any], order: int) -> RuntimeGraphNode:
    tool_name = _string(record.get("tool_name")) or "Tool"
    return RuntimeGraphNode(
        id=_node_id("tool", record, order, preferred=tool_name),
        type="tool",
        label=tool_name,
        status=_string(record.get("status") or record.get("decision")) or "success",
        timestamp=_timestamp(record, "timestamp", "created_at"),
        duration_ms=_duration_ms(record),
        summary=_tool_summary(record),
        metadata={"source": "tool_audit.jsonl", "raw": record},
    )


def _trace_node(record: dict[str, Any], order: int) -> RuntimeGraphNode:
    action = str(record.get("action_type") or "trace_step")
    observation = record.get("observation") if isinstance(record.get("observation"), dict) else {}
    return RuntimeGraphNode(
        id=_node_id("trace", record, order),
        type=_node_type_for_kind(action),
        label=_title(action),
        status=_string(record.get("status")) or "success",
        timestamp=_timestamp(record, "created_at", "timestamp"),
        duration_ms=_duration_ms(record) or record.get("latency_ms"),
        summary=_trace_summary(record),
        metadata={
            "source": "trace.jsonl",
            "raw": record,
            "url_before": record.get("url_before"),
            "url_after": record.get("url_after"),
            "title_after": record.get("title"),
            "screenshot_path": record.get("screenshot_path"),
            "readiness": observation.get("readiness"),
        },
    )


def _approval_node(record: dict[str, Any], order: int) -> RuntimeGraphNode:
    approval_id = _string(record.get("approval_id"))
    return RuntimeGraphNode(
        id=_node_id("approval", record, order, preferred=approval_id),
        type="approval",
        label=f"Approval: {record.get('status') or 'pending'}",
        status=_string(record.get("status")) or "blocked",
        timestamp=_timestamp(record, "created_at", "decided_at", "timestamp"),
        summary=_string(record.get("reason")),
        metadata={"source": "approvals.jsonl", "raw": record},
    )


def _recovery_node(record: dict[str, Any], order: int) -> RuntimeGraphNode:
    kind = str(record.get("kind") or record.get("event_type") or "recovery")
    return RuntimeGraphNode(
        id=_node_id("recovery", record, order),
        type="recovery",
        label=_title(kind),
        status=_string(record.get("status") or record.get("outcome")) or "running",
        timestamp=_timestamp(record, "timestamp", "created_at"),
        duration_ms=_duration_ms(record),
        summary=_summary(record),
        metadata={"source": "recovery.jsonl", "raw": record},
    )


def _evidence_node(record: dict[str, Any], order: int) -> RuntimeGraphNode:
    evidence_id = _string(record.get("evidence_id")) or f"evidence_{order}"
    kind = str(record.get("kind") or "evidence")
    return RuntimeGraphNode(
        id=_node_id("evidence", record, order, preferred=evidence_id),
        type="evidence",
        label=f"Evidence: {kind}",
        status="success",
        timestamp=_timestamp(record, "created_at", "timestamp"),
        summary=_summary(record) or _string(record.get("source_url")),
        metadata={
            "source": "evidence.jsonl",
            "raw": record,
            "evidence_id": evidence_id,
            "screenshot_path": record.get("screenshot_path"),
            "step_id": record.get("step_id") or record.get("trace_event_id"),
        },
    )


def _report_node(report_text: str, order: int) -> RuntimeGraphNode:
    return RuntimeGraphNode(
        id=f"report_{order:06d}",
        type="report",
        label="Final Report",
        status="success",
        summary=_preview(report_text, 260),
        metadata={"source": "final_report.md"},
    )


def _sequence_edges(nodes: list[RuntimeGraphNode]) -> list[RuntimeGraphEdge]:
    edges: list[RuntimeGraphEdge] = []
    for index, (source, target) in enumerate(zip(nodes, nodes[1:]), start=1):
        edges.append(
            RuntimeGraphEdge(
                id=f"edge_sequence_{index:06d}",
                source=source.id,
                target=target.id,
                type="sequence",
                label=None,
            )
        )
    return edges


def _evidence_edges(nodes: list[RuntimeGraphNode]) -> list[RuntimeGraphEdge]:
    by_step: dict[str, RuntimeGraphNode] = {}
    edges: list[RuntimeGraphEdge] = []
    for node in nodes:
        raw = node.metadata.get("raw")
        if isinstance(raw, dict):
            step_id = _string(raw.get("step_id") or raw.get("trace_event_id"))
            if step_id and node.type != "evidence":
                by_step[step_id] = node
    for node in nodes:
        if node.type != "evidence":
            continue
        step_id = _string(node.metadata.get("step_id"))
        source = by_step.get(step_id or "")
        if source is None:
            continue
        edges.append(
            RuntimeGraphEdge(
                id=f"edge_produced_{_slug(source.id)}_{_slug(node.id)}",
                source=source.id,
                target=node.id,
                type="produced",
                label="produced",
            )
        )
    return edges


def _dedupe_nodes(nodes: list[RuntimeGraphNode]) -> list[RuntimeGraphNode]:
    seen: set[str] = set()
    result: list[RuntimeGraphNode] = []
    for node in nodes:
        base = node.id
        node_id = base
        suffix = 2
        while node_id in seen:
            node_id = f"{base}_{suffix}"
            suffix += 1
        seen.add(node_id)
        result.append(node if node_id == node.id else node.model_copy(update={"id": node_id}))
    return result


def _dedupe_edges(edges: list[RuntimeGraphEdge]) -> list[RuntimeGraphEdge]:
    seen: set[str] = set()
    result: list[RuntimeGraphEdge] = []
    for edge in edges:
        if edge.id in seen:
            continue
        seen.add(edge.id)
        result.append(edge)
    return result


def _node_type_for_kind(kind: str) -> str:
    if kind in {"task_created", "task_started", "task_succeeded", "task_finished", "task_failed", "task_blocked"}:
        return "task"
    if kind.startswith("workflow_"):
        return "workflow"
    if kind.startswith("planner_"):
        return "planner"
    if kind.startswith("llm_"):
        return "llm"
    if kind.startswith("tool_") or kind.startswith("risk_"):
        return "tool"
    if kind.startswith("browser_") or kind.startswith("navigation_") or kind.startswith("action_") or kind.startswith("post_action_"):
        return "browser"
    if kind.startswith("readiness_") or kind == "readiness_check":
        return "readiness"
    if kind.startswith("effect_verification") or kind == "effect_verify":
        return "verifier"
    if kind.startswith("recovery_"):
        return "recovery"
    if "evidence" in kind:
        return "evidence"
    if "approval" in kind:
        return "approval"
    if "report" in kind:
        return "report"
    if "failed" in kind or "error" in kind:
        return "error"
    return "workflow"


def _status_for_event(kind: str, payload: dict[str, Any]) -> str:
    status = _string(payload.get("status"))
    if status:
        return status
    if kind.endswith("_started"):
        return "running"
    if kind.endswith("_failed") or kind in {"task_failed", "llm_action_rejected"}:
        return "failed"
    if kind in {"approval_required", "task_paused", "task_blocked"}:
        return "blocked"
    if kind.endswith("_finished") or kind.endswith("_succeeded") or kind in {"task_succeeded", "report_generated", "report_written", "evidence_added"}:
        return "success"
    return "success"


def _label_for_kind(kind: str, payload: dict[str, Any]) -> str:
    tool_name = _string(payload.get("tool_name"))
    if tool_name and kind.startswith("tool_"):
        return f"{_title(kind)}: {tool_name}"
    action_type = _string(payload.get("action_type"))
    if action_type and kind.startswith("llm_action"):
        return f"{_title(kind)}: {action_type}"
    return _title(kind)


def _timestamp(record: dict[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = record.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def _node_id(
    prefix: str,
    record: dict[str, Any],
    order: int,
    *,
    preferred: str | None = None,
) -> str:
    if preferred:
        return f"{prefix}_{_slug(preferred)}"
    for key in ("event_id", "call_id", "step_id", "approval_id", "evidence_id", "attempt_id"):
        value = record.get(key)
        if isinstance(value, str) and value:
            return f"{prefix}_{_slug(value)}"
    return f"{prefix}_{order:06d}"


def _duration_ms(record: dict[str, Any]) -> int | float | None:
    for key in ("duration_ms", "latency_ms", "elapsed_ms"):
        value = record.get(key)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return value
    return None


def _summary(record: Any) -> str | None:
    if not isinstance(record, dict):
        return _preview(record)
    for key in ("summary", "message", "error", "error_message", "reason"):
        value = record.get(key)
        if isinstance(value, str) and value:
            return value
    return _preview(record)


def _tool_summary(record: dict[str, Any]) -> str:
    decision = record.get("decision") or "decision unknown"
    risk = record.get("risk_level") or "risk unknown"
    duration = _duration_ms(record)
    suffix = f" · {duration}ms" if duration is not None else ""
    return f"{decision} / {risk}{suffix}"


def _trace_summary(record: dict[str, Any]) -> str | None:
    if record.get("error_message"):
        return _string(record.get("error_message"))
    before = _string(record.get("url_before"))
    after = _string(record.get("url_after"))
    if before and after and before != after:
        return f"{before} -> {after}"
    return _string(record.get("title")) or _summary(record)


def _evidence_ids(record: dict[str, Any]) -> list[str]:
    payload = record.get("payload") if isinstance(record.get("payload"), dict) else record
    result: list[str] = []
    for key in ("evidence_id", "screenshot_evidence_id"):
        value = payload.get(key)
        if isinstance(value, str) and value:
            result.append(value)
    ids = payload.get("evidence_ids")
    if isinstance(ids, list):
        result.extend(str(item) for item in ids if item)
    return result


def _title(kind: str) -> str:
    return kind.replace("_", " ").strip().title()


def _string(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _preview(value: Any, limit: int = 240) -> str | None:
    if value is None:
        return None
    compact = " ".join(str(value).split())
    if not compact:
        return None
    return compact if len(compact) <= limit else compact[: limit - 1] + "..."


def _slug(value: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in value).strip("_") or "item"
