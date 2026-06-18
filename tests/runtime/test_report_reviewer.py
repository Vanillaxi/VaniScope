from __future__ import annotations

from webscoper.runtime.evidence import EvidenceStore
from webscoper.runtime.reviewer import ReportReviewer, build_review_summary_markdown
from webscoper.schemas.action import ExpectedEffect
from webscoper.schemas.task import TaskSpec


def test_report_reviewer_passes_with_existing_evidence_reference() -> None:
    store = _store()
    report = """# Report

## Result

Task completed. [ev_000001]

## Evidence

- [ev_000001] Page observation.
"""

    result = ReportReviewer().review(report, store.list_items())

    assert result.passed
    assert result.score == 1.0
    assert result.issues == []
    assert result.claim_checks[0].supported


def test_report_reviewer_errors_on_missing_evidence_reference() -> None:
    report = """# Report

## Result

Task completed. [ev_999999]

## Evidence

- [ev_999999] Missing.
"""

    result = ReportReviewer().review(report, _store().list_items())

    assert not result.passed
    assert _issue_types(result) == ["missing_evidence_reference"]


def test_report_reviewer_errors_on_missing_evidence_section() -> None:
    result = ReportReviewer().review(
        """# Report

## Result

Task completed. [ev_000001]
""",
        _store().list_items(),
    )

    assert not result.passed
    assert "missing_evidence_section" in _issue_types(result)


def test_report_reviewer_warns_on_unsupported_result_claim() -> None:
    result = ReportReviewer().review(
        """# Report

## Result

The page contains installation instructions.

## Evidence

- [ev_000001] Page observation.
""",
        _store().list_items(),
    )

    assert result.passed
    assert "unsupported_claim" in _issue_types(result)


def test_report_reviewer_errors_on_empty_evidence() -> None:
    result = ReportReviewer().review(
        """# Report

## Result

Task completed.

## Evidence

- No evidence.
""",
        [],
    )

    assert not result.passed
    assert "empty_evidence" in _issue_types(result)


def test_report_reviewer_checks_expected_content() -> None:
    task = TaskSpec(
        task_id="review_task",
        raw_input="Expect text.",
        target_url="file:///tmp/basic.html",
        expected_effect=ExpectedEffect(
            type="content_appears",
            value="pip install playwright",
        ),
    )
    result = ReportReviewer().review(
        """# Report

## Result

Task completed. [ev_000001]

## Evidence

- [ev_000001] Page observation.
""",
        _store(text="Quickstart").list_items(),
        task_spec=task,
    )

    assert result.passed
    assert "expected_content_not_found" in _issue_types(result)


def test_review_summary_markdown_contains_status_and_claims() -> None:
    result = ReportReviewer().review(
        """# Report

## Result

Task completed. [ev_000001]

## Evidence

- [ev_000001] Page observation.
""",
        _store().list_items(),
    )

    summary = build_review_summary_markdown(result)

    assert "# VaniScope Review Summary" in summary
    assert "PASSED" in summary
    assert "ev_000001" in summary


def _store(text: str = "Quickstart") -> EvidenceStore:
    store = EvidenceStore()
    store.add_item(
        kind="page_observation",
        source_url="file:///tmp/basic.html",
        page_title="Basic",
        text=text,
    )
    return store


def _issue_types(result) -> list[str]:
    return [issue.issue_type for issue in result.issues]
