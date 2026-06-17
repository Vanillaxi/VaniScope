from __future__ import annotations

import json
from pathlib import Path

from webscoper.runtime.reviewer import ReportReviewer
from webscoper.schemas.action import ExpectedEffect
from webscoper.schemas.evidence import EvidenceItem
from webscoper.schemas.eval import (
    ReviewerEvalCase,
    ReviewerEvalCaseResult,
    ReviewerEvalSummary,
)
from webscoper.schemas.task import TaskSpec


class ReviewerEvalRunner:
    def __init__(self, reviewer: ReportReviewer | None = None) -> None:
        self.reviewer = reviewer or ReportReviewer()

    def run_cases(self, cases: list[ReviewerEvalCase]) -> ReviewerEvalSummary:
        results = [self._run_case(case) for case in cases]
        total = len(results)
        passed = sum(1 for result in results if result.passed)
        average_score = (
            sum(result.score for result in results) / total
            if total
            else 0.0
        )
        return ReviewerEvalSummary(
            total=total,
            passed=passed,
            failed=total - passed,
            pass_rate=passed / total if total else 0.0,
            average_review_score=average_score,
            case_results=results,
        )

    def run_file(self, cases_path: Path) -> ReviewerEvalSummary:
        payload = json.loads(cases_path.read_text(encoding="utf-8"))
        cases = [ReviewerEvalCase.model_validate(item) for item in payload]
        return self.run_cases(cases)

    def _run_case(self, case: ReviewerEvalCase) -> ReviewerEvalCaseResult:
        try:
            evidence_items = [
                EvidenceItem.model_validate(item)
                for item in case.evidence_items
            ]
            review = self.reviewer.review(
                case.report_markdown,
                evidence_items,
                task_spec=_task_spec_for_case(case),
            )
            actual_issue_types = [issue.issue_type for issue in review.issues]
            expected_issue_types = case.expected.issue_types
            missing_issue_types = [
                issue_type
                for issue_type in expected_issue_types
                if issue_type not in actual_issue_types
            ]
            unexpected_issue_types = [
                issue_type
                for issue_type in actual_issue_types
                if issue_type not in expected_issue_types
            ]
            passed = _expectations_passed(
                reviewer_passed=review.passed,
                score=review.score,
                expected_passed=case.expected.passed,
                min_score=case.expected.min_score,
                max_score=case.expected.max_score,
                missing_issue_types=missing_issue_types,
            )
            return ReviewerEvalCaseResult(
                case_id=case.case_id,
                passed=passed,
                reviewer_passed=review.passed,
                score=review.score,
                expected_passed=case.expected.passed,
                expected_issue_types=expected_issue_types,
                actual_issue_types=actual_issue_types,
                missing_issue_types=missing_issue_types,
                unexpected_issue_types=unexpected_issue_types,
            )
        except Exception as exc:
            return ReviewerEvalCaseResult(
                case_id=case.case_id,
                passed=False,
                reviewer_passed=False,
                score=0.0,
                expected_passed=case.expected.passed,
                expected_issue_types=case.expected.issue_types,
                error=f"{type(exc).__name__}: {exc}",
            )


def write_reviewer_eval_outputs(
    summary: ReviewerEvalSummary,
    output_dir: Path,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "score.json").write_text(
        json.dumps(summary.model_dump(mode="json"), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    (output_dir / "report.md").write_text(
        _report_markdown(summary),
        encoding="utf-8",
    )


def _expectations_passed(
    reviewer_passed: bool,
    score: float,
    expected_passed: bool | None,
    min_score: float | None,
    max_score: float | None,
    missing_issue_types: list[str],
) -> bool:
    if expected_passed is not None and reviewer_passed != expected_passed:
        return False
    if min_score is not None and score < min_score:
        return False
    if max_score is not None and score > max_score:
        return False
    return not missing_issue_types


def _report_markdown(summary: ReviewerEvalSummary) -> str:
    lines = [
        "# VaniScope Reviewer Eval Report",
        "",
        "## Summary",
        "",
        f"- Total: {summary.total}",
        f"- Passed: {summary.passed}",
        f"- Failed: {summary.failed}",
        f"- Pass rate: {summary.pass_rate:.4f}",
        f"- Average review score: {summary.average_review_score:.4f}",
        "",
        "## Cases",
        "",
        "| Case | Eval Passed | Reviewer Passed | Score | Issues |",
        "|---|---:|---:|---:|---|",
    ]
    for result in summary.case_results:
        issues = ", ".join(result.actual_issue_types)
        lines.append(
            "| {case_id} | {eval_passed} | {reviewer_passed} | {score:.2f} | {issues} |".format(
                case_id=result.case_id,
                eval_passed="yes" if result.passed else "no",
                reviewer_passed="yes" if result.reviewer_passed else "no",
                score=result.score,
                issues=issues,
            )
        )
    lines.append("")
    return "\n".join(lines)


def _task_spec_for_case(case: ReviewerEvalCase) -> TaskSpec | None:
    if not case.expected_text:
        return None
    return TaskSpec(
        task_id=case.case_id,
        raw_input=case.description,
        target_url="file://reviewer-eval",
        expected_effect=ExpectedEffect(
            type="content_appears",
            value=case.expected_text,
        ),
    )
