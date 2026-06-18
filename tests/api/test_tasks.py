from __future__ import annotations

from tests.helpers import basic_task_request


def test_api_task_lifecycle(api_client) -> None:
    client = api_client
    create_response = client.post(
        "/tasks",
        json=basic_task_request(),
    )

    assert create_response.status_code == 200
    payload = create_response.json()
    task_id = payload["task_id"]
    assert payload["status"] == "succeeded"
    assert "final_report.md" in payload["artifacts"]
    assert "review.json" in payload["artifacts"]

    status_response = client.get(f"/tasks/{task_id}")
    assert status_response.status_code == 200
    assert status_response.json()["status"] == "succeeded"

    artifacts_response = client.get(f"/tasks/{task_id}/artifacts")
    assert artifacts_response.status_code == 200
    artifacts = artifacts_response.json()["artifacts"]
    assert "final_report.md" in artifacts
    assert "evidence.jsonl" in artifacts

    report_response = client.get(f"/tasks/{task_id}/artifacts/final_report.md")
    assert report_response.status_code == 200
    assert "# VaniScope Task Report" in report_response.json()["content"]


def test_api_artifact_traversal_rejected(api_client) -> None:
    client = api_client
    response = client.get("/tasks/missing/artifacts/..%2F..%2F.env")

    assert response.status_code in {400, 404}
