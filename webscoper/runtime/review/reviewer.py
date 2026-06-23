from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from webscoper.runtime.llm.reviewer import BaseLLMReportReviewer
from webscoper.schemas.artifact import EvidenceItem
from webscoper.schemas.review import (
    ClaimEvidenceCheck,
    LLMReviewRequest,
    LLMReviewResult,
    RevisionAction,
    RevisionPlan,
    RevisionResult,
    ReviseLoopResult,
    ReviewIssue,
    ReviewResult,
)
from webscoper.schemas.task import TaskSpec


class ReportReviewer:
    def review(
        self,
        report_markdown: str,
        evidence_items: list[EvidenceItem],
        task_spec: TaskSpec | None = None,
    ) -> ReviewResult:
        builder = _IssueBuilder()
        evidence_ids = {item.evidence_id for item in evidence_items}
        referenced_ids = _evidence_refs(report_markdown)
        claim_checks = _claim_checks(report_markdown)

        if not evidence_items:
            builder.add(
                severity="error",
                issue_type="empty_evidence",
                message="No evidence items were available for review.",
            )

        if not _has_heading(report_markdown, "Evidence", "证据链"):
            builder.add(
                severity="error",
                issue_type="missing_evidence_section",
                message="Report is missing the Evidence / 证据链 section.",
                location="report",
            )

        if not _has_heading(report_markdown, "Result", "核心结论"):
            builder.add(
                severity="warning",
                issue_type="missing_result_section",
                message="Report is missing the Result / 核心结论 section.",
                location="report",
            )

        if task_spec is not None and task_spec.skill_id == "docs_research":
            if not _has_heading(report_markdown, "Source URL", "来源页面"):
                builder.add(
                    severity="error",
                    issue_type="missing_source_url_section",
                    message="Docs research report is missing the ## Source URL section.",
                    location="report",
                )
            if not _has_source_url(report_markdown, evidence_items, task_spec.target_url):
                builder.add(
                    severity="error",
                    issue_type="missing_source_url",
                    message="Docs research report does not include the source URL.",
                    location="## Source URL",
                )
            query = task_spec.query or task_spec.research_goal
            if query and not _contains_query_terms(query, report_markdown, evidence_items):
                builder.add(
                    severity="warning",
                    issue_type="query_not_answered",
                    message=f"Report does not appear to answer query: {query}.",
                    location="report",
                )

        if task_spec is not None and task_spec.skill_id == "github_issue_research":
            if not _has_heading(report_markdown, "Source URL", "来源页面"):
                builder.add(
                    severity="error",
                    issue_type="missing_source_url_section",
                    message="GitHub issue research report is missing the ## Source URL section.",
                    location="report",
                )
            if not _has_source_url(report_markdown, evidence_items, task_spec.target_url):
                builder.add(
                    severity="error",
                    issue_type="missing_source_url",
                    message="GitHub issue research report does not include the source URL.",
                    location="## Source URL",
                )
            for heading, issue_type in {
                "Affected Modules": "missing_affected_modules",
                "Difficulty Estimate": "missing_difficulty",
                "Contribution Value": "missing_contribution_value",
                "Final Recommendation": "missing_recommendation",
            }.items():
                if not _has_heading(report_markdown, heading, _zh_github_heading(heading)):
                    builder.add(
                        severity="error",
                        issue_type=issue_type,
                        message=f"GitHub issue research report is missing ## {heading}.",
                        location="report",
                    )
            if not (
                _section_has_content(report_markdown, "Affected Modules")
                or _section_has_content(report_markdown, "影响模块")
            ):
                builder.add(
                    severity="error",
                    issue_type="empty_affected_modules",
                    message="Affected modules section is empty.",
                    location="## Affected Modules",
                )
            difficulty_section = _section(report_markdown, "Difficulty Estimate") or _section(
                report_markdown,
                "难度判断",
            )
            if not re.search(r"\b(low|medium|high)\b|[低中高]", difficulty_section, re.I):
                builder.add(
                    severity="error",
                    issue_type="difficulty_not_classified",
                    message="Difficulty estimate must include low, medium, or high.",
                    location="## Difficulty Estimate",
                )
            contribution_section = _section(report_markdown, "Contribution Value") or _section(
                report_markdown,
                "贡献价值",
            )
            if not re.search(r"\b(low|medium|high)\b|[低中高]", contribution_section, re.I):
                builder.add(
                    severity="error",
                    issue_type="contribution_value_not_classified",
                    message="Contribution value must include low, medium, or high.",
                    location="## Contribution Value",
                )
            query = task_spec.query or task_spec.research_goal
            if query and not _contains_query_terms(query, report_markdown, evidence_items):
                builder.add(
                    severity="warning",
                    issue_type="query_not_answered",
                    message=f"Report does not appear to answer query: {query}.",
                    location="report",
                )

        for evidence_id in referenced_ids:
            if evidence_id not in evidence_ids:
                builder.add(
                    severity="error",
                    issue_type="missing_evidence_reference",
                    message=f"Report references unknown evidence id: {evidence_id}.",
                    evidence_id=evidence_id,
                    location="report",
                )

        for check in claim_checks:
            if not check.supported:
                builder.add(
                    severity="warning",
                    issue_type="unsupported_claim",
                    message="Result claim does not cite an evidence id.",
                    location="## Result",
                    metadata={"claim": check.claim},
                )

        expected_text = _expected_text(task_spec)
        if expected_text and not _contains_expected(
            expected_text,
            report_markdown,
            evidence_items,
        ):
            builder.add(
                severity="warning",
                issue_type="expected_content_not_found",
                message=f"Expected content was not found in report or evidence: {expected_text}.",
                location="task.expected_effect",
            )

        issues = builder.issues
        score = _score(issues)
        passed = not any(issue.severity == "error" for issue in issues)
        return ReviewResult(
            passed=passed,
            score=score,
            issues=issues,
            claim_checks=claim_checks,
            summary=_summary(passed, score, issues),
            metadata={
                "evidence_count": len(evidence_items),
                "referenced_evidence_ids": referenced_ids,
                "skill_id": task_spec.skill_id if task_spec is not None else None,
            },
        )


def build_review_summary_markdown(result: ReviewResult) -> str:
    lines = [
        "# VaniScope Review Summary",
        "",
        "## Status",
        "",
        "PASSED" if result.passed else "FAILED",
        "",
        "## Score",
        "",
        f"{result.score:.2f}",
        "",
        "## Issues",
        "",
    ]
    if result.issues:
        for issue in result.issues:
            lines.append(
                f"- [{issue.severity}] {issue.issue_type}: {issue.message}"
            )
    else:
        lines.append("- No issues found.")

    lines.extend(["", "## Claim Checks", ""])
    if result.claim_checks:
        for check in result.claim_checks:
            evidence = ", ".join(check.evidence_ids) if check.evidence_ids else "none"
            lines.extend(
                [
                    f"- claim: {check.claim}",
                    f"  evidence: {evidence}",
                    f"  supported: {str(check.supported).lower()}",
                ]
            )
    else:
        lines.append("- No claims detected.")
    lines.append("")
    return "\n".join(lines)


class _IssueBuilder:
    def __init__(self) -> None:
        self.issues: list[ReviewIssue] = []

    def add(
        self,
        severity: str,
        issue_type: str,
        message: str,
        evidence_id: str | None = None,
        location: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.issues.append(
            ReviewIssue(
                issue_id=f"rv_{len(self.issues) + 1:06d}",
                severity=severity,  # type: ignore[arg-type]
                issue_type=issue_type,
                message=message,
                evidence_id=evidence_id,
                location=location,
                metadata=metadata or {},
            )
        )


def _evidence_refs(markdown: str) -> list[str]:
    return sorted(set(re.findall(r"\bev_\d{6}\b", markdown)))


def _claim_checks(markdown: str) -> list[ClaimEvidenceCheck]:
    section = _section(markdown, "Result")
    if not section:
        return []

    claims: list[ClaimEvidenceCheck] = []
    for claim in _claims_from_section(section):
        refs = _evidence_refs(claim)
        supported = bool(refs) or _is_allowed_short_claim(claim)
        claims.append(
            ClaimEvidenceCheck(
                claim=claim,
                evidence_ids=refs,
                supported=supported,
                reason="Evidence id cited." if refs else "No evidence id cited.",
            )
        )
    return claims


def _has_heading(markdown: str, *headings: str | None) -> bool:
    for heading in headings:
        if not heading:
            continue
        pattern = rf"(?im)^##\s+{re.escape(heading)}\s*$"
        if re.search(pattern, markdown):
            return True
    return False


def _zh_github_heading(heading: str) -> str | None:
    return {
        "Affected Modules": "影响模块",
        "Difficulty Estimate": "难度判断",
        "Contribution Value": "贡献价值",
        "Final Recommendation": "最终建议",
    }.get(heading)


def _section(markdown: str, heading: str) -> str:
    pattern = rf"(?ms)^## {re.escape(heading)}\s*$\n(?P<body>.*?)(?=^## |\Z)"
    match = re.search(pattern, markdown)
    return match.group("body").strip() if match else ""


def _claims_from_section(section: str) -> list[str]:
    claims: list[str] = []
    for line in section.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("- "):
            claims.append(stripped[2:].strip())
            continue
        if _evidence_refs(stripped):
            claims.append(stripped)
            continue
        claims.extend(_sentence_claims(stripped))
    return [claim for claim in claims if claim]


def _sentence_claims(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+", text)
    return [part.strip() for part in parts if part.strip()]


def _is_allowed_short_claim(claim: str) -> bool:
    normalized = claim.strip().lower().rstrip(".")
    return normalized in {"task completed", "completed", "done"} or len(normalized) < 20


def _expected_text(task_spec: TaskSpec | None) -> str | None:
    if task_spec is None:
        return None
    if task_spec.expected_effect is not None and task_spec.expected_effect.value:
        return task_spec.expected_effect.value
    if (
        task_spec.action is not None
        and task_spec.action.expected_effect is not None
        and task_spec.action.expected_effect.value
    ):
        return task_spec.action.expected_effect.value
    return None


def _contains_expected(
    expected_text: str,
    report_markdown: str,
    evidence_items: list[EvidenceItem],
) -> bool:
    needle = expected_text.lower()
    if needle in report_markdown.lower():
        return True
    return any(needle in (item.text or "").lower() for item in evidence_items)


def _has_source_url(
    report_markdown: str,
    evidence_items: list[EvidenceItem],
    target_url: str,
) -> bool:
    candidates = {target_url}
    candidates.update(item.source_url for item in evidence_items if item.source_url)
    return any(candidate and candidate in report_markdown for candidate in candidates)


def _contains_query_terms(
    query: str,
    report_markdown: str,
    evidence_items: list[EvidenceItem],
) -> bool:
    terms = _query_terms(query)
    if not terms:
        return True
    text = report_markdown.lower() + "\n" + "\n".join(
        (item.text or "").lower() for item in evidence_items
    )
    return any(term in text for term in terms)


def _section_has_content(markdown: str, heading: str) -> bool:
    section = _section(markdown, heading)
    if not section:
        return False
    return any(line.strip().startswith("- ") for line in section.splitlines())


def _query_terms(query: str) -> set[str]:
    terms = re.findall(r"[a-zA-Z0-9_]+|[\u4e00-\u9fff]{2,}", query.lower())
    stop = {"how", "do", "i", "the", "and", "run", "with", "what", "does", "如何"}
    return {term for term in terms if len(term) > 1 and term not in stop}


def _score(issues: list[ReviewIssue]) -> float:
    score = 1.0
    for issue in issues:
        if issue.severity == "error":
            score -= 0.35
        elif issue.severity == "warning":
            score -= 0.15
        else:
            score -= 0.05
    return max(0.0, round(score, 4))


def _summary(passed: bool, score: float, issues: list[ReviewIssue]) -> str:
    status = "passed" if passed else "failed"
    return f"Review {status} with score {score:.2f} and {len(issues)} issue(s)."


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
                revised = _append_section(
                    revised,
                    action.replacement or _evidence_section(evidence_items),
                )
            elif action.action_type == "add_missing_result":
                if "## Result" in revised:
                    skipped.append(action)
                    continue
                revised = _insert_after_title(
                    revised,
                    action.replacement or "## Result\n\nTask completed.",
                )
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


class ReviewReviseLoop:
    def __init__(
        self,
        deterministic_reviewer: ReportReviewer,
        revision_planner: ReviewRevisionPlanner,
        report_reviser: ReportReviser,
        llm_reviewer: BaseLLMReportReviewer | None = None,
        max_revisions: int = 1,
    ) -> None:
        self.deterministic_reviewer = deterministic_reviewer
        self.revision_planner = revision_planner
        self.report_reviser = report_reviser
        self.llm_reviewer = llm_reviewer
        self.max_revisions = max(0, max_revisions)

    def run(
        self,
        *,
        task_id: str | None,
        task_goal: str | None,
        report_markdown: str,
        evidence_items: list[EvidenceItem],
        compact_context: dict[str, Any] | None = None,
        output_dir: Path | None = None,
    ) -> ReviseLoopResult:
        initial_review = self.deterministic_reviewer.review(report_markdown, evidence_items)
        llm_review = None
        if self.llm_reviewer is not None:
            llm_review = self.llm_reviewer.review(
                LLMReviewRequest(
                    task_id=task_id,
                    task_goal=task_goal,
                    report_markdown=report_markdown,
                    evidence_items=[item.model_dump(mode="json") for item in evidence_items],
                    compact_context=compact_context,
                    deterministic_review=initial_review.model_dump(mode="json"),
                    instructions=[
                        "Review strictly against available evidence ids.",
                        "Do not invent evidence or claims.",
                    ],
                )
            )

        plan = (
            self.revision_planner.build_plan(
                report_markdown=report_markdown,
                deterministic_review=initial_review,
                llm_review=llm_review,
                evidence_items=evidence_items,
            )
            if self.max_revisions > 0
            else RevisionPlan(actions=[], summary="Revision attempts disabled.")
        )
        revision = self.report_reviser.apply_plan(report_markdown, plan, evidence_items)
        final_review = self.deterministic_reviewer.review(
            revision.revised_report_markdown,
            evidence_items,
        )

        result = ReviseLoopResult(
            task_id=task_id,
            initial_review=initial_review.model_dump(mode="json"),
            llm_review=llm_review,
            revision_plan=plan,
            revision_result=revision,
            final_review=final_review.model_dump(mode="json"),
            passed=final_review.passed,
            artifacts=[],
            metadata={
                "max_revisions": self.max_revisions,
                "revised": revision.revised,
            },
        )
        if output_dir is not None:
            result = _write_artifacts(result, output_dir)
        return result


def _write_artifacts(result: ReviseLoopResult, output_dir: Path) -> ReviseLoopResult:
    output_dir.mkdir(parents=True, exist_ok=True)
    artifacts: list[str] = []
    if result.llm_review is not None:
        _write_json(output_dir / "llm_review.json", result.llm_review.model_dump(mode="json"))
        artifacts.append("llm_review.json")
    _write_json(output_dir / "revision_plan.json", result.revision_plan.model_dump(mode="json"))
    artifacts.append("revision_plan.json")
    (output_dir / "revised_report.md").write_text(
        result.revision_result.revised_report_markdown,
        encoding="utf-8",
    )
    artifacts.append("revised_report.md")
    _write_json(output_dir / "final_review.json", result.final_review)
    artifacts.append("final_review.json")
    updated = result.model_copy(update={"artifacts": artifacts + ["revise_loop.json"]})
    _write_json(output_dir / "revise_loop.json", updated.model_dump(mode="json"))
    return updated


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


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
