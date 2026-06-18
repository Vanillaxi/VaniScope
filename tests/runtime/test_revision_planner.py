from __future__ import annotations

from webscoper.runtime.reviewer import ReportReviewer
from webscoper.runtime.revision import ReviewRevisionPlanner
from webscoper.schemas.evidence import EvidenceItem


def test_revision_planner_adds_missing_sections_and_evidence_reference() -> None:
    evidence = [_evidence("ev_000001")]
    report = "# Report\n\n## Result\n\nThe install command was found."
    review = ReportReviewer().review(report, evidence)

    plan = ReviewRevisionPlanner().build_plan(
        report_markdown=report,
        deterministic_review=review,
        llm_review=None,
        evidence_items=evidence,
    )

    action_types = [action.action_type for action in plan.actions]
    assert "add_missing_evidence_section" in action_types
    assert "add_evidence_reference" in action_types


def test_revision_planner_replaces_unknown_evidence_reference() -> None:
    evidence = [_evidence("ev_000001")]
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

    rewrite = [action for action in plan.actions if action.action_type == "rewrite_claim"]
    assert rewrite
    assert rewrite[0].target == "ev_999999"
    assert rewrite[0].replacement == "ev_000001"


def _evidence(evidence_id: str) -> EvidenceItem:
    return EvidenceItem(
        evidence_id=evidence_id,
        kind="text_excerpt",
        source_url="file:///tmp/basic.html",
        text="pip install playwright",
        created_at="2026-01-01T00:00:00+00:00",
    )
