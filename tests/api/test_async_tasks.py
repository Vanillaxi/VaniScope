from __future__ import annotations

from tests.helpers import basic_task_request, wait_for_terminal_status


def test_api_async_task_lifecycle_and_events(api_client) -> None:
    client = api_client
    create_response = client.post(
        "/tasks/async",
        json=basic_task_request(),
    )

    assert create_response.status_code == 200
    created = create_response.json()
    task_id = created["task_id"]
    assert created["status"] == "running"
    assert created["artifacts"] == []

    status_payload = wait_for_terminal_status(client, task_id)
    assert status_payload["status"] == "succeeded"
    assert "events.jsonl" in status_payload["artifacts"]
    assert "final_report.md" in status_payload["artifacts"]

    events_response = client.get(f"/tasks/{task_id}/events")
    assert events_response.status_code == 200
    assert events_response.headers["content-type"].startswith("text/event-stream")
    body = events_response.text
    assert "event: task_started" in body
    assert "event: task_finished" in body

    artifacts_response = client.get(f"/tasks/{task_id}/artifacts")
    assert artifacts_response.status_code == 200
    assert "events.jsonl" in artifacts_response.json()["artifacts"]
