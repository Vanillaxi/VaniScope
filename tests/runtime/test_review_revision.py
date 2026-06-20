from __future__ import annotations

# From test_report_reviewer.py
from webscoper.runtime.artifacts.evidence import EvidenceStore
from webscoper.runtime.review.reviewer import ReportReviewer, build_review_summary_markdown
from webscoper.schemas.browser import ExpectedEffect
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


def test_report_reviewer_detects_core_issue_types() -> None:
    cases = [
        (
            """# Report

## Result

Task completed. [ev_999999]

## Evidence

- [ev_999999] Missing.
""",
            _store().list_items(),
            "missing_evidence_reference",
            False,
        ),
        (
            """# Report

## Result

Task completed. [ev_000001]
""",
            _store().list_items(),
            "missing_evidence_section",
            False,
        ),
        (
            """# Report

## Result

The page contains installation instructions.

## Evidence

- [ev_000001] Page observation.
""",
            _store().list_items(),
            "unsupported_claim",
            True,
        ),
        (
            """# Report

## Result

Task completed.

## Evidence

- No evidence.
""",
            [],
            "empty_evidence",
            False,
        ),
    ]

    for report, evidence, issue_type, passed in cases:
        result = ReportReviewer().review(report, evidence)
        assert result.passed is passed
        assert issue_type in _issue_types(result)


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

# From test_report_reviser.py
from webscoper.runtime.review.reviewer import ReportReviewer
from webscoper.runtime.review.revision import ReportReviser, ReviewRevisionPlanner
from webscoper.schemas.artifact import EvidenceItem


def test_report_reviser_adds_and_rewrites_evidence_references() -> None:
    evidence = [_evidence("ev_000001")]
    missing_reference_report = "# Report\n\n## Result\n\nThe install command was found."
    unknown_reference_report = (
        "# Report\n\n## Result\n\n- Task completed [ev_999999]\n\n"
        "## Evidence\n\n- [ev_999999] missing"
    )

    for report in [missing_reference_report, unknown_reference_report]:
        review = ReportReviewer().review(report, evidence)
        plan = ReviewRevisionPlanner().build_plan(
            report_markdown=report,
            deterministic_review=review,
            llm_review=None,
            evidence_items=evidence,
        )
        result = ReportReviser().apply_plan(report, plan, evidence)
        assert result.revised is True
        assert "ev_000001" in result.revised_report_markdown
        assert "ev_999999" not in result.revised_report_markdown


def _evidence(evidence_id: str) -> EvidenceItem:
    return EvidenceItem(
        evidence_id=evidence_id,
        kind="text_excerpt",
        source_url="file:///tmp/basic.html",
        text="pip install playwright",
        created_at="2026-01-01T00:00:00+00:00",
    )

# From test_revise_loop.py
import json
from pathlib import Path

from webscoper.runtime.llm.reviewer import FakeLLMReportReviewer
from webscoper.runtime.review.reviewer import ReportReviewer
from webscoper.runtime.review.revise_loop import ReviewReviseLoop
from webscoper.runtime.review.revision import ReportReviser, ReviewRevisionPlanner
from webscoper.schemas.artifact import EvidenceItem


def test_revise_loop_writes_artifacts_and_final_review(tmp_path: Path) -> None:
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
    loop = ReviewReviseLoop(
        deterministic_reviewer=ReportReviewer(),
        revision_planner=ReviewRevisionPlanner(),
        report_reviser=ReportReviser(),
        llm_reviewer=FakeLLMReportReviewer(),
        max_revisions=1,
    )

    result = loop.run(
        task_id="task_x",
        task_goal="Click Quickstart",
        report_markdown=report,
        evidence_items=evidence,
        compact_context={"context_pack": {"task_id": "task_x"}},
        output_dir=tmp_path,
    )

    assert result.revision_result.revised is True
    assert result.final_review["passed"] is True
    assert (tmp_path / "llm_review.json").exists()
    assert (tmp_path / "revision_plan.json").exists()
    assert (tmp_path / "revised_report.md").exists()
    assert (tmp_path / "final_review.json").exists()
    assert (tmp_path / "revise_loop.json").exists()
    loop_payload = json.loads((tmp_path / "revise_loop.json").read_text())
    assert "revised_report.md" in loop_payload["artifacts"]
