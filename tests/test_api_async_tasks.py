from __future__ import annotations

import time
from pathlib import Path

from fastapi.testclient import TestClient

import webscoper.api.app as api_module
from webscoper.api.task_service import TaskService


def test_api_async_task_lifecycle_and_events(tmp_path: Path) -> None:
    api_module.task_service = TaskService(runs_dir=tmp_path / "runs")

    with TestClient(api_module.app) as client:
        create_response = client.post(
            "/tasks/async",
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
        created = create_response.json()
        task_id = created["task_id"]
        assert created["status"] == "running"
        assert created["artifacts"] == []

        status_payload = _wait_for_terminal_status(client, task_id)
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


def _wait_for_terminal_status(
    client: TestClient,
    task_id: str,
    timeout_seconds: float = 10.0,
) -> dict:
    deadline = time.monotonic() + timeout_seconds
    last_payload: dict = {}
    while time.monotonic() < deadline:
        response = client.get(f"/tasks/{task_id}")
        assert response.status_code == 200
        last_payload = response.json()
        if last_payload["status"] in {"succeeded", "failed"}:
            return last_payload
        time.sleep(0.1)
    raise AssertionError(f"Task did not finish before timeout: {last_payload}")
