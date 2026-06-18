from __future__ import annotations

from pathlib import Path

from webscoper.runtime.events import TaskEventStore
from webscoper.schemas.events import TaskEvent


def test_task_event_store_appends_and_lists_events(tmp_path: Path) -> None:
    store = TaskEventStore()

    first = store.append(
        TaskEvent(
            task_id="task_test",
            kind="task_started",
            message="Task started",
        )
    )
    second = store.append(
        TaskEvent(
            task_id="task_test",
            kind="prompt_built",
            message="Prompt built",
            payload={"ok": True},
        )
    )

    assert first.event_id == "evt_000001"
    assert second.event_id == "evt_000002"
    assert first.created_at
    assert store.list_events("task_test") == [first, second]

    output_path = tmp_path / "events.jsonl"
    store.write_jsonl("task_test", output_path)

    lines = output_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert "evt_000001" in lines[0]
