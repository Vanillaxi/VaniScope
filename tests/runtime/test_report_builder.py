from __future__ import annotations

from webscoper.runtime.evidence import EvidenceStore
from webscoper.runtime.report import FinalReportBuilder
from webscoper.schemas.task import TaskSpec


def test_final_report_builder_includes_evidence_ids() -> None:
    store = EvidenceStore()
    store.add_item(
        kind="page_observation",
        source_url="file:///tmp/basic.html",
        page_title="Basic",
        text="Quickstart",
    )
    task = TaskSpec(
        task_id="report_task",
        raw_input="Open local basic mock.",
        target_url="file:///tmp/basic.html",
    )

    report = FinalReportBuilder().build_markdown(task, store.list_items())

    assert "# VaniScope Task Report" in report
    assert "report_task" in report
    assert "ev_000001" in report
    assert "Page observation" in report
