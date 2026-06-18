from __future__ import annotations

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
