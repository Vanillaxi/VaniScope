from __future__ import annotations

import json
from pathlib import Path

from webscoper.api.task_service import ARTIFACT_ALLOWLIST
from webscoper.runtime.execution.handler import WebAgentExecutionHandler
from webscoper.runtime.prompt.reminders import RuntimeReminderStore
from webscoper.runtime.execution.runner import build_task_spec


def test_run_task_writes_recovery_artifact_and_events(tmp_path: Path) -> None:
    reminders = RuntimeReminderStore()
    reminders.add("Use recovery if the target is not immediately available.")
    handler = WebAgentExecutionHandler(
        output_root=tmp_path,
        workspace=Path("tests/fixtures/workspace"),
        runtime_reminders=reminders,
        planner_mode="deterministic",
        run_id_override="recovery_task",
    )
    task = build_task_spec(
        url="tests/fixtures/mock_site/lazy_button.html",
        click="Quickstart",
        expect="pip install playwright",
        task_id="recovery_task",
    )

    handler.run_sync(task)

    run_dir = tmp_path / "recovery_task"
    assert "recovery.jsonl" in ARTIFACT_ALLOWLIST
    assert (run_dir / "recovery.jsonl").exists()
    transcript_events = [
        item["event_type"] for item in _read_jsonl(run_dir / "transcript.jsonl")
    ]
    assert "recovery_started" in transcript_events
    assert "recovery_succeeded" in transcript_events


def _read_jsonl(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
