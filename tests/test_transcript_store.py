from __future__ import annotations

import json
from pathlib import Path

from webscoper.runtime.transcript import TranscriptStore


def test_transcript_store_appends_jsonl_event(tmp_path: Path) -> None:
    store = TranscriptStore(run_dir=tmp_path / "run", run_id="run_test")

    store.append("task_loaded", {"task_id": "test"})

    assert store.transcript_path.exists()
    lines = store.transcript_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1

    event = json.loads(lines[0])
    assert event["run_id"] == "run_test"
    assert event["event_type"] == "task_loaded"
    assert event["payload"]["task_id"] == "test"
    assert event["created_at"]
