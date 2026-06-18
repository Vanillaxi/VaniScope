from __future__ import annotations

from pathlib import Path

from webscoper.eval.reviewer_eval import ReviewerEvalRunner


def test_reviewer_eval_runner_scores_fixture_cases() -> None:
    summary = ReviewerEvalRunner().run_file(
        Path("tests/fixtures/reviewer_eval_cases.json")
    )
    results = {result.case_id: result for result in summary.case_results}

    assert summary.total >= 8
    assert summary.passed == summary.total
    assert summary.failed == 0
    assert summary.pass_rate == 1.0
    assert summary.average_review_score > 0
    assert results["valid_report_with_evidence"].passed
    assert "missing_evidence_reference" in results[
        "unknown_evidence_reference"
    ].actual_issue_types
    assert "unsupported_claim" in results["unsupported_claim"].actual_issue_types
    assert "expected_content_not_found" in results[
        "expected_content_not_found"
    ].actual_issue_types
