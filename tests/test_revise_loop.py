from __future__ import annotations

import json
from pathlib import Path

from webscoper.runtime.llm_reviewer import FakeLLMReportReviewer
from webscoper.runtime.reviewer import ReportReviewer
from webscoper.runtime.revise_loop import ReviewReviseLoop
from webscoper.runtime.revision import ReportReviser, ReviewRevisionPlanner
from webscoper.schemas.evidence import EvidenceItem


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
