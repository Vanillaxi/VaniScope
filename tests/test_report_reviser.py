from __future__ import annotations

from webscoper.runtime.reviewer import ReportReviewer
from webscoper.runtime.revision import ReportReviser, ReviewRevisionPlanner
from webscoper.schemas.evidence import EvidenceItem


def test_report_reviser_generates_revised_report_with_valid_evidence_id() -> None:
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
    review = ReportReviewer().review(report, evidence)
    plan = ReviewRevisionPlanner().build_plan(
        report_markdown=report,
        deterministic_review=review,
        llm_review=None,
        evidence_items=evidence,
    )

    result = ReportReviser().apply_plan(report, plan, evidence)

    assert result.revised is True
    assert "## Evidence" in result.revised_report_markdown
    assert "ev_000001" in result.revised_report_markdown
    assert result.applied_actions


def test_report_reviser_replaces_unknown_evidence_id() -> None:
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
        "# Report\n\n## Result\n\n- Task completed [ev_999999]\n\n"
        "## Evidence\n\n- [ev_999999] missing"
    )
    review = ReportReviewer().review(report, evidence)
    plan = ReviewRevisionPlanner().build_plan(
        report_markdown=report,
        deterministic_review=review,
        llm_review=None,
        evidence_items=evidence,
    )

    result = ReportReviser().apply_plan(report, plan, evidence)

    assert "ev_999999" not in result.revised_report_markdown
    assert "ev_000001" in result.revised_report_markdown
