from __future__ import annotations

import re
from typing import Any

from webscoper.schemas.artifact import EvidenceItem
from webscoper.schemas.review import ClaimEvidenceCheck, ReviewIssue, ReviewResult
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

        if "## Evidence" not in report_markdown:
            builder.add(
                severity="error",
                issue_type="missing_evidence_section",
                message="Report is missing the ## Evidence section.",
                location="report",
            )

        if "## Result" not in report_markdown:
            builder.add(
                severity="warning",
                issue_type="missing_result_section",
                message="Report is missing the ## Result section.",
                location="report",
            )

        if task_spec is not None and task_spec.skill_id == "docs_research":
            if "## Source URL" not in report_markdown:
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
            if "## Source URL" not in report_markdown:
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
                if f"## {heading}" not in report_markdown:
                    builder.add(
                        severity="error",
                        issue_type=issue_type,
                        message=f"GitHub issue research report is missing ## {heading}.",
                        location="report",
                    )
            if not _section_has_content(report_markdown, "Affected Modules"):
                builder.add(
                    severity="error",
                    issue_type="empty_affected_modules",
                    message="Affected modules section is empty.",
                    location="## Affected Modules",
                )
            if not re.search(r"\b(low|medium|high)\b", _section(report_markdown, "Difficulty Estimate"), re.I):
                builder.add(
                    severity="error",
                    issue_type="difficulty_not_classified",
                    message="Difficulty estimate must include low, medium, or high.",
                    location="## Difficulty Estimate",
                )
            if not re.search(r"\b(low|medium|high)\b", _section(report_markdown, "Contribution Value"), re.I):
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
