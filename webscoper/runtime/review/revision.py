from __future__ import annotations

from typing import Any

from webscoper.schemas.artifact import EvidenceItem
from webscoper.schemas.review import ReviewResult
from webscoper.schemas.review import (
    LLMReviewResult,
    RevisionAction,
    RevisionPlan,
    RevisionResult,
)


class ReviewRevisionPlanner:
    def build_plan(
        self,
        *,
        report_markdown: str,
        deterministic_review: ReviewResult,
        llm_review: LLMReviewResult | None,
        evidence_items: list[EvidenceItem],
    ) -> RevisionPlan:
        actions: list[RevisionAction] = []
        first_evidence_id = evidence_items[0].evidence_id if evidence_items else None

        if "## Evidence" not in report_markdown:
            actions.append(
                RevisionAction(
                    action_type="add_missing_evidence_section",
                    replacement=_evidence_section(evidence_items),
                    evidence_ids=[item.evidence_id for item in evidence_items],
                    reason="Report is missing ## Evidence; add deterministic evidence references.",
                )
            )

        if "## Result" not in report_markdown:
            replacement = "## Result\n\nTask completed. See evidence references below."
            if first_evidence_id:
                replacement += f" [{first_evidence_id}]"
            actions.append(
                RevisionAction(
                    action_type="add_missing_result",
                    replacement=replacement,
                    evidence_ids=[first_evidence_id] if first_evidence_id else [],
                    reason="Report is missing ## Result; add a concise evidence-grounded result.",
                )
            )

        known_ids = {item.evidence_id for item in evidence_items}
        for issue in deterministic_review.issues:
            if issue.issue_type == "unsupported_claim":
                claim = _claim_from_issue(issue.metadata)
                if first_evidence_id and claim:
                    actions.append(
                        RevisionAction(
                            action_type="add_evidence_reference",
                            target=claim,
                            replacement=f"{claim} [{first_evidence_id}]",
                            evidence_ids=[first_evidence_id],
                            reason=(
                                "Heuristic: unsupported claim had no evidence id; "
                                "append the first available evidence reference."
                            ),
                        )
                    )
                elif claim:
                    actions.append(
                        RevisionAction(
                            action_type="remove_unsupported_claim",
                            target=claim,
                            reason="Unsupported claim could not be matched to evidence.",
                        )
                    )
                continue

            if issue.issue_type == "missing_evidence_reference" and issue.evidence_id:
                replacement = first_evidence_id if first_evidence_id in known_ids else None
                actions.append(
                    RevisionAction(
                        action_type="rewrite_claim",
                        target=issue.evidence_id,
                        replacement=replacement,
                        evidence_ids=[replacement] if replacement else [],
                        reason=(
                            "Report referenced an unknown evidence id; replace with the "
                            "first available evidence id or remove the reference."
                        ),
                    )
                )

        if llm_review is not None:
            for finding in llm_review.findings:
                if finding.issue_type in {
                    "missing_evidence_section",
                    "missing_result_section",
                    "unsupported_claim",
                    "missing_evidence_reference",
                }:
                    continue
                actions.append(
                    RevisionAction(
                        action_type="no_op",
                        evidence_ids=finding.evidence_ids,
                        reason=f"LLM finding recorded without deterministic action: {finding.issue_type}",
                        metadata={"finding": finding.model_dump(mode="json")},
                    )
                )

        summary = (
            f"Revision plan has {len(actions)} action(s)."
            if actions
            else "No revision actions required."
        )
        return RevisionPlan(
            actions=actions,
            summary=summary,
            metadata={
                "deterministic_issue_count": len(deterministic_review.issues),
                "llm_finding_count": len(llm_review.findings) if llm_review else 0,
            },
        )


class ReportReviser:
    def apply_plan(
        self,
        report_markdown: str,
        plan: RevisionPlan,
        evidence_items: list[EvidenceItem],
    ) -> RevisionResult:
        revised = report_markdown
        applied: list[RevisionAction] = []
        skipped: list[RevisionAction] = []

        for action in plan.actions:
            before = revised
            if action.action_type == "add_missing_evidence_section":
                if "## Evidence" in revised:
                    skipped.append(action)
                    continue
                revised = _append_section(revised, action.replacement or _evidence_section(evidence_items))
            elif action.action_type == "add_missing_result":
                if "## Result" in revised:
                    skipped.append(action)
                    continue
                revised = _insert_after_title(revised, action.replacement or "## Result\n\nTask completed.")
            elif action.action_type == "add_evidence_reference":
                if not action.target or not action.replacement:
                    skipped.append(action)
                    continue
                revised = revised.replace(action.target, action.replacement, 1)
            elif action.action_type == "rewrite_claim":
                if not action.target:
                    skipped.append(action)
                    continue
                if action.replacement:
                    revised = revised.replace(action.target, action.replacement)
                else:
                    revised = revised.replace(f" [{action.target}]", "")
                    revised = revised.replace(action.target, "")
            elif action.action_type == "remove_unsupported_claim":
                if not action.target:
                    skipped.append(action)
                    continue
                revised = _remove_line_containing(revised, action.target)
            elif action.action_type == "no_op":
                skipped.append(action)
                continue

            if revised != before:
                applied.append(action)
            else:
                skipped.append(action)

        return RevisionResult(
            revised=bool(applied),
            revised_report_markdown=revised,
            applied_actions=applied,
            skipped_actions=skipped,
            summary=(
                f"Applied {len(applied)} revision action(s); skipped {len(skipped)}."
                if applied
                else "No report changes were applied."
            ),
            metadata={"plan_id": plan.plan_id},
        )


def _evidence_section(evidence_items: list[EvidenceItem]) -> str:
    lines = ["## Evidence", ""]
    if not evidence_items:
        lines.append("- No evidence items available.")
        return "\n".join(lines)
    for item in evidence_items:
        source = item.source_url or "unknown source"
        preview = _preview(item.text, 160) or item.kind
        lines.append(f"- [{item.evidence_id}] {preview} ({source})")
    return "\n".join(lines)


def _append_section(markdown: str, section: str) -> str:
    return markdown.rstrip() + "\n\n" + section.strip() + "\n"


def _insert_after_title(markdown: str, section: str) -> str:
    lines = markdown.splitlines()
    if lines and lines[0].startswith("# "):
        return "\n".join([lines[0], "", section.strip(), "", *lines[1:]]).rstrip() + "\n"
    return section.strip() + "\n\n" + markdown.rstrip() + "\n"


def _remove_line_containing(markdown: str, target: str) -> str:
    lines = [line for line in markdown.splitlines() if target not in line]
    return "\n".join(lines).rstrip() + "\n"


def _claim_from_issue(metadata: dict[str, Any]) -> str | None:
    claim = metadata.get("claim")
    if claim is None:
        return None
    text = str(claim).strip()
    return text or None


def _preview(value: str | None, limit: int) -> str | None:
    if value is None:
        return None
    text = " ".join(value.split())
    if not text:
        return None
    return text if len(text) <= limit else text[:limit].rstrip()
