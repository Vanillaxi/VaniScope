from __future__ import annotations

import sqlite3
from pathlib import Path

from tests.helpers import mock_site_path, wait_for_terminal_status


def test_conversation_messages_and_task_metadata_persist(api_client, tmp_path) -> None:
    client = api_client
    conversation_response = client.post(
        "/conversations",
        json={"title": "Research session", "metadata_json": {"source": "test"}},
    )
    assert conversation_response.status_code == 200
    conversation = conversation_response.json()

    create_response = client.post(
        "/tasks/async",
        json={
            "url": mock_site_path("basic.html"),
            "conversation_id": conversation["id"],
            "goal": "Summarize the visible quickstart information.",
            "mode": "auto_explore",
            "planner": "fake_llm",
            "workspace": "tests/fixtures/workspace",
            "max_steps": 5,
        },
    )
    assert create_response.status_code == 200
    task_id = create_response.json()["task_id"]
    status = wait_for_terminal_status(client, task_id)
    assert status["status"] == "succeeded"

    messages_response = client.get(f"/conversations/{conversation['id']}/messages")
    assert messages_response.status_code == 200
    messages = messages_response.json()
    assert [message["role"] for message in messages] == ["user", "assistant"]
    assert messages[0]["task_id"] == task_id

    db_path = Path(tmp_path) / "vaniscope.db"
    assert db_path.exists()
    with sqlite3.connect(db_path) as conn:
        task_count = conn.execute("SELECT count(*) FROM tasks WHERE id = ?", (task_id,)).fetchone()[0]
        artifact_count = conn.execute(
            "SELECT count(*) FROM artifacts WHERE task_id = ?",
            (task_id,),
        ).fetchone()[0]
    assert task_count == 1
    assert artifact_count > 0
