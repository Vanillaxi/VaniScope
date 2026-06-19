from __future__ import annotations

from tests.helpers import basic_task_request


def test_api_task_timeline_returns_timeline(api_client) -> None:
    create_response = api_client.post("/tasks", json=basic_task_request())
    assert create_response.status_code == 200
    task_id = create_response.json()["task_id"]

    response = api_client.get(f"/tasks/{task_id}/timeline")

    assert response.status_code == 200
    payload = response.json()
    assert payload["task_id"] == task_id
    assert payload["summary"]["timeline_count"] > 0
    assert any(item["category"] == "workflow" for item in payload["timeline_items"])
    assert any(item["category"] == "evidence" for item in payload["timeline_items"])


def test_api_task_timeline_rejects_path_traversal(api_client) -> None:
    response = api_client.get("/tasks/%2E%2E/timeline")

    assert response.status_code in {400, 404}
