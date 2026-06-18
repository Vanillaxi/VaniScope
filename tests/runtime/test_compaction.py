from __future__ import annotations

# From test_context_compactor.py
import json
from pathlib import Path

from webscoper.runtime.compaction import ContextCompactor
from webscoper.schemas.compaction import CompactionPolicy
from webscoper.schemas.evidence import EvidenceItem
from webscoper.schemas.risk import ApprovalRequest


def test_context_compactor_should_compact_when_transcript_exceeds_threshold() -> None:
    compactor = ContextCompactor(
        CompactionPolicy(max_transcript_events=2, max_trace_events=10)
    )

    assert compactor.should_compact([{}, {}, {}]) is True
    assert compactor.should_compact([{}]) is False


def test_context_compactor_builds_context_pack_with_evidence_refs() -> None:
    evidence = EvidenceItem(
        evidence_id="ev_000001",
        kind="page_observation",
        source_url="file:///tmp/basic.html",
        page_title="Basic",
        text="pip install playwright " * 30,
        screenshot_path="/tmp/basic.png",
        created_at="2026-01-01T00:00:00+00:00",
    )
    trace = [
        {
            "step_id": "step_001",
            "action_type": "browser_final_observe",
            "status": "success",
            "url_after": "file:///tmp/basic.html",
            "title": "Basic",
            "screenshot_path": "/tmp/basic.png",
            "observation": {
                "url": "file:///tmp/basic.html",
                "title": "Basic",
                "visible_text_summary": "Quickstart Install pip install playwright",
                "screenshot_path": "/tmp/basic.png",
            },
        }
    ]

    result = ContextCompactor().compact(
        task_id="task_x",
        task_goal="Click Quickstart",
        transcript_events=[{"event_type": "task_loaded", "payload": {}}],
        trace_events=trace,
        evidence_items=[evidence],
    )

    pack = result.context_pack
    assert pack.task_id == "task_x"
    assert pack.current_state is not None
    assert pack.current_state.current_url == "file:///tmp/basic.html"
    assert pack.evidence_refs[0].evidence_id == "ev_000001"
    assert pack.evidence_refs[0].source_url == "file:///tmp/basic.html"
    assert pack.evidence_refs[0].text_preview is not None
    assert len(pack.evidence_refs[0].text_preview) <= 300


def test_context_compactor_summarizes_recovery_and_risk_state() -> None:
    approval = ApprovalRequest(
        approval_id="appr_000001",
        task_id="task_x",
        status="pending",
        reason="Approval required",
        risk_level="sensitive",
    )
    result = ContextCompactor().compact(
        task_id="task_x",
        task_goal="Click Continue",
        transcript_events=[],
        recovery_attempts=[
            {"attempt_id": "rec_1", "status": "succeeded"},
            {"attempt_id": "rec_2", "status": "failed"},
            {"attempt_id": "rec_3", "status": "blocked"},
        ],
        approval_requests=[approval],
        risk_report={
            "blocked": 1,
            "signals": [{"kind": "external_submit", "message": "Submit action"}],
        },
    )

    recovery = result.context_pack.recovery_state
    risk = result.context_pack.risk_state
    assert recovery is not None
    assert recovery.total_attempts == 3
    assert recovery.recovered_count == 1
    assert recovery.failed_count == 1
    assert recovery.blocked_count == 1
    assert risk is not None
    assert risk.has_pending_approval is True
    assert risk.pending_approval_ids == ["appr_000001"]
    assert risk.blocked is True
    assert risk.risk_signals[0]["kind"] == "external_submit"


def test_context_compactor_writes_artifacts(tmp_path: Path) -> None:
    compactor = ContextCompactor()
    result = compactor.compact(
        task_id="task_x",
        task_goal="Do a local task",
        transcript_events=[],
    )

    compactor.write_artifacts(result, tmp_path)

    context = json.loads((tmp_path / "compact_context.json").read_text())
    summary = (tmp_path / "compact_summary.md").read_text()
    assert context["context_pack"]["task_id"] == "task_x"
    assert "# Compact Runtime Context" in summary

# From test_compaction_artifacts.py
import json
from pathlib import Path

from webscoper.runtime.execution import WebAgentExecutionHandler
from webscoper.runtime.task_runner import build_task_spec


def test_execution_handler_writes_compaction_artifacts(tmp_path: Path) -> None:
    handler = WebAgentExecutionHandler(
        output_root=tmp_path,
        workspace=Path("tests/fixtures/workspace"),
        planner_mode="deterministic",
        run_id_override="compact_task",
    )
    task = build_task_spec(
        url="tests/fixtures/mock_site/basic.html",
        click="Quickstart",
        expect="pip install playwright",
        task_id="compact_task",
    )

    handler.run_sync(task)

    run_dir = tmp_path / "compact_task"
    compact_context_path = run_dir / "compact_context.json"
    compact_summary_path = run_dir / "compact_summary.md"
    assert compact_context_path.exists()
    assert compact_summary_path.exists()
    context = json.loads(compact_context_path.read_text())
    assert context["context_pack"]["task_id"] == "compact_task"
    assert context["context_pack"]["evidence_refs"]
    assert "Compact Runtime Context" in compact_summary_path.read_text()
    transcript_events = [
        json.loads(line)["event_type"]
        for line in (run_dir / "transcript.jsonl").read_text().splitlines()
    ]
    assert "compaction_written" in transcript_events
