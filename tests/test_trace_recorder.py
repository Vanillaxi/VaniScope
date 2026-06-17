from __future__ import annotations

import json
from pathlib import Path

from webscoper.runtime.trace import TraceRecorder
from webscoper.schemas.trace import TraceStep


def test_trace_recorder_appends_jsonl(tmp_path: Path) -> None:
    recorder = TraceRecorder(run_dir=tmp_path / "run_test", run_id="run_test")
    step = TraceStep(
        step_id="step_001",
        run_id="run_test",
        phase="browser_runtime",
        actor="system",
        action_type="browser_open_observe",
        status="success",
    )

    recorder.record(step)

    assert recorder.trace_path.exists()
    lines = recorder.trace_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    payload = json.loads(lines[0])
    assert payload["action_type"] == "browser_open_observe"
