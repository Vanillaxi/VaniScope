from __future__ import annotations

import json

from webscoper.runtime.inspector.loader import RunArtifactLoader
from webscoper.runtime.inspector.timeline import RuntimeTimelineBuilder


def test_runtime_timeline_builder_tolerates_missing_artifacts(tmp_path) -> None:
    run_dir = tmp_path / "runs" / "task_empty"
    run_dir.mkdir(parents=True)

    response = RuntimeTimelineBuilder(
        RunArtifactLoader(tmp_path / "runs", "task_empty"),
        status="succeeded",
    ).build_timeline_response()

    assert response.task_id == "task_empty"
    assert response.summary.status == "succeeded"
    assert response.timeline_items == []


def test_runtime_timeline_builder_merges_and_sorts_artifacts(tmp_path) -> None:
    run_dir = tmp_path / "runs" / "task_timeline"
    run_dir.mkdir(parents=True)
    _write_jsonl(
        run_dir / "events.jsonl",
        [
            {
                "event_id": "evt_001",
                "task_id": "task_timeline",
                "kind": "workflow_started",
                "message": "Workflow started",
                "created_at": "2026-01-01T00:00:01+00:00",
                "payload": {},
            }
        ],
    )
    _write_jsonl(
        run_dir / "tool_audit.jsonl",
        [
            {
                "timestamp": "2026-01-01T00:00:02+00:00",
                "task_id": "task_timeline",
                "workflow_backend": "langgraph",
                "tool_name": "browser_open_observe",
                "decision": "allow",
                "status": "success",
                "risk_level": "safe",
            }
        ],
    )
    _write_jsonl(
        run_dir / "llm_calls.jsonl",
        [
            {
                "timestamp": "2026-01-01T00:00:03+00:00",
                "task_id": "task_timeline",
                "provider": "fake",
                "model": "fake-planner",
                "mode": "fake",
                "purpose": "planner",
                "status": "success",
                "budget_decision": "allowed",
            }
        ],
    )
    _write_jsonl(
        run_dir / "recovery.jsonl",
        [
            {
                "timestamp": "2026-01-01T00:00:04+00:00",
                "kind": "recovery_started",
                "status": "running",
                "failed_step_id": "step_001",
            }
        ],
    )
    _write_jsonl(
        run_dir / "evidence.jsonl",
        [
            {
                "evidence_id": "ev_000001",
                "kind": "text_excerpt",
                "source_url": "file:///mock.html",
                "page_title": "Mock",
                "text": "Evidence text",
                "created_at": "2026-01-01T00:00:05+00:00",
            }
        ],
    )
    (run_dir / "final_report.md").write_text(
        "# Report\n\nUses ev_000001.\n",
        encoding="utf-8",
    )

    inspector = RuntimeTimelineBuilder(
        RunArtifactLoader(tmp_path / "runs", "task_timeline"),
        status="succeeded",
    ).build_inspector_response()

    assert [item.category for item in inspector.timeline_items[:5]] == [
        "workflow",
        "tool",
        "llm",
        "recovery",
        "evidence",
    ]
    assert inspector.summary.llm_call_count == 1
    assert inspector.summary.budget_decisions == {"allowed": 1}
    assert inspector.summary.recovery_count == 1
    assert inspector.summary.evidence_count == 1
    assert inspector.evidence_links[0].report_sections == ["Report"]
    assert inspector.report_summary["title"] == "Report"
    assert inspector.evidence_summary["total_count"] == 1
    assert inspector.tool_summary["total_calls"] == 1
    assert inspector.llm_summary["estimated_tokens"] == 0
    assert inspector.recovery_summary["recovery_attempts"] == 1
    assert any(
        item.artifact_name == "events.jsonl" and item.developer_only
        for item in inspector.artifact_presentations
    )


def _write_jsonl(path, rows: list[dict]) -> None:
    path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )
