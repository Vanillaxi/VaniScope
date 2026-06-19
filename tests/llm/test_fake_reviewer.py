from __future__ import annotations

from webscoper.runtime.llm.reviewer import FakeLLMReportReviewer
from webscoper.runtime.review.reviewer import ReportReviewer
from webscoper.schemas.artifact import EvidenceItem
from webscoper.schemas.review import LLMReviewRequest


def test_fake_llm_reviewer_generates_findings_from_deterministic_review() -> None:
    evidence = [
        EvidenceItem(
            evidence_id="ev_000001",
            kind="text_excerpt",
            source_url="file:///tmp/basic.html",
            text="pip install playwright",
            created_at="2026-01-01T00:00:00+00:00",
        )
    ]
    report = "# Report\n\n## Result\n\nThe install command was found."
    deterministic = ReportReviewer().review(report, evidence)

    result = FakeLLMReportReviewer().review(
        LLMReviewRequest(
            task_id="task_x",
            task_goal="Click Quickstart",
            report_markdown=report,
            evidence_items=[item.model_dump(mode="json") for item in evidence],
            deterministic_review=deterministic.model_dump(mode="json"),
        )
    )

    issue_types = {finding.issue_type for finding in result.findings}
    assert "missing_evidence_section" in issue_types
    assert "unsupported_claim" in issue_types
    assert result.summary.startswith("Fake LLM reviewer found")


def test_fake_llm_reviewer_passes_clean_review() -> None:
    evidence = [
        EvidenceItem(
            evidence_id="ev_000001",
            kind="text_excerpt",
            source_url="file:///tmp/basic.html",
            text="pip install playwright",
            created_at="2026-01-01T00:00:00+00:00",
        )
    ]
    report = (
        "# Report\n\n## Result\n\n- Task completed [ev_000001]\n\n"
        "## Evidence\n\n- [ev_000001] pip install playwright"
    )
    deterministic = ReportReviewer().review(report, evidence)

    result = FakeLLMReportReviewer().review(
        LLMReviewRequest(
            report_markdown=report,
            evidence_items=[item.model_dump(mode="json") for item in evidence],
            deterministic_review=deterministic.model_dump(mode="json"),
        )
    )

    assert result.passed is True
    assert result.findings == []
