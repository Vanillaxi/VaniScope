from __future__ import annotations

import re
from typing import Any

from webscoper.runtime.inspector.schemas import RuntimeEvidenceLink


EVIDENCE_REF_RE = re.compile(r"\b(ev_\d{6}|evidence[_-]?\d+)\b", re.IGNORECASE)


class RuntimeArtifactLinker:
    def __init__(
        self,
        *,
        evidence: list[dict[str, Any]] | None = None,
        final_report: str = "",
        review: dict[str, Any] | None = None,
        tool_audit: list[dict[str, Any]] | None = None,
        llm_calls: list[dict[str, Any]] | None = None,
        trace: list[dict[str, Any]] | None = None,
        approvals: list[dict[str, Any]] | None = None,
    ) -> None:
        self.evidence = evidence or []
        self.final_report = final_report
        self.review = review or {}
        self.tool_audit = tool_audit or []
        self.llm_calls = llm_calls or []
        self.trace = trace or []
        self.approvals = approvals or []

    def evidence_links(self) -> list[RuntimeEvidenceLink]:
        report_sections = _report_sections_by_evidence(self.final_report)
        review_issue_ids = _review_issues_by_evidence(self.review)
        links: list[RuntimeEvidenceLink] = []
        for item in self.evidence:
            evidence_id = str(item.get("evidence_id") or "")
            if not evidence_id:
                continue
            text = item.get("text")
            links.append(
                RuntimeEvidenceLink(
                    evidence_id=evidence_id,
                    source_url=_string_or_none(item.get("source_url")),
                    page_title=_string_or_none(item.get("page_title")),
                    text_preview=_preview(text),
                    report_sections=report_sections.get(evidence_id, []),
                    review_issue_ids=review_issue_ids.get(evidence_id, []),
                    raw=item,
                )
            )
        return links

    def tool_audit_by_name(self) -> dict[str, list[dict[str, Any]]]:
        result: dict[str, list[dict[str, Any]]] = {}
        for item in self.tool_audit:
            tool_name = _string_or_none(item.get("tool_name"))
            if tool_name:
                result.setdefault(tool_name, []).append(item)
        return result

    def approval_by_id(self) -> dict[str, dict[str, Any]]:
        result: dict[str, dict[str, Any]] = {}
        for item in self.approvals:
            approval_id = _string_or_none(item.get("approval_id"))
            if approval_id:
                result[approval_id] = item
        return result

    def trace_by_step_id(self) -> dict[str, dict[str, Any]]:
        result: dict[str, dict[str, Any]] = {}
        for item in self.trace:
            step_id = _string_or_none(item.get("step_id"))
            if step_id:
                result[step_id] = item
        return result

    def llm_call_by_index(self) -> dict[str, dict[str, Any]]:
        return {f"llm_{index:06d}": item for index, item in enumerate(self.llm_calls, start=1)}


def evidence_ids_from_payload(payload: Any) -> list[str]:
    try:
        text = str(payload)
    except Exception:
        return []
    return sorted(set(match.group(1) for match in EVIDENCE_REF_RE.finditer(text)))


def _report_sections_by_evidence(report_text: str) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    current_heading = "Report"
    for line in report_text.splitlines():
        if line.startswith("#"):
            current_heading = line.strip("# ").strip() or current_heading
        for evidence_id in evidence_ids_from_payload(line):
            result.setdefault(evidence_id, [])
            if current_heading not in result[evidence_id]:
                result[evidence_id].append(current_heading)
    return result


def _review_issues_by_evidence(review: dict[str, Any]) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    candidates = []
    for key in ("issues", "findings", "unsupported_claims"):
        value = review.get(key)
        if isinstance(value, list):
            candidates.extend(value)
    for index, issue in enumerate(candidates, start=1):
        issue_id = (
            str(issue.get("issue_id") or issue.get("id"))
            if isinstance(issue, dict)
            else f"issue_{index:03d}"
        )
        for evidence_id in evidence_ids_from_payload(issue):
            result.setdefault(evidence_id, [])
            if issue_id not in result[evidence_id]:
                result[evidence_id].append(issue_id)
    return result


def _string_or_none(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _preview(value: Any, limit: int = 240) -> str | None:
    if not isinstance(value, str) or not value:
        return None
    compact = " ".join(value.split())
    return compact if len(compact) <= limit else compact[: limit - 1] + "…"
