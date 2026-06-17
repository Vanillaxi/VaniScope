from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

import webscoper.api.app as api_module
from webscoper.api.task_service import TaskService


def test_api_task_lifecycle(tmp_path: Path) -> None:
    api_module.task_service = TaskService(runs_dir=tmp_path / "runs")
    client = TestClient(api_module.app)

    create_response = client.post(
        "/tasks",
        json={
            "url": "tests/fixtures/mock_site/basic.html",
            "click": "Quickstart",
            "expect": "pip install playwright",
            "planner": "deterministic",
            "workspace": "tests/fixtures/workspace",
            "reminder": "This is a test runtime reminder.",
        },
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


def test_api_artifact_traversal_rejected(tmp_path: Path) -> None:
    api_module.task_service = TaskService(runs_dir=tmp_path / "runs")
    client = TestClient(api_module.app)

    response = client.get("/tasks/missing/artifacts/..%2F..%2F.env")

    assert response.status_code in {400, 404}
