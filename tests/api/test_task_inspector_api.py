from __future__ import annotations

from tests.helpers import basic_task_request


def test_api_task_inspector_returns_aggregates(api_client) -> None:
    create_response = api_client.post("/tasks", json=basic_task_request())
    assert create_response.status_code == 200
    task_id = create_response.json()["task_id"]

    response = api_client.get(f"/tasks/{task_id}/inspector")

    assert response.status_code == 200
    payload = response.json()
    assert payload["task_id"] == task_id
    assert payload["status"] == "succeeded"
    assert payload["summary"]["evidence_count"] >= 1
    assert payload["evidence_links"]
    assert payload["llm_summary"]["call_count"] == 0
    assert payload["review_summary"]["available"] is True
    assert payload["approval_summary"]["count"] == 0
