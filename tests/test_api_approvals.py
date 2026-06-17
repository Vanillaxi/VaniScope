from __future__ import annotations

import time
from pathlib import Path

from fastapi.testclient import TestClient

import webscoper.api.app as api_module
from webscoper.api.task_service import TaskService


def test_api_lists_and_decides_task_approval(tmp_path: Path) -> None:
    api_module.task_service = TaskService(runs_dir=tmp_path / "runs")

    with TestClient(api_module.app) as client:
        task_id = _create_async_risk_task(client, click="Submit")
        status_payload = _wait_for_status(client, task_id, "requires_approval")

        assert status_payload["status"] == "requires_approval"
        assert "approvals.jsonl" in status_payload["artifacts"]
        assert "risk_report.json" in status_payload["artifacts"]

        events_response = client.get(f"/tasks/{task_id}/events")
        assert events_response.status_code == 200
        assert "event: approval_required" in events_response.text
        assert "event: task_paused" in events_response.text

        approvals_response = client.get(f"/tasks/{task_id}/approvals")
        assert approvals_response.status_code == 200
        approvals = approvals_response.json()
        assert len(approvals) == 1
        approval_id = approvals[0]["approval_id"]
        assert approvals[0]["status"] == "pending"
        assert approvals[0]["target_hint"] == "Submit"

        approval_response = client.get(f"/approvals/{approval_id}")
        assert approval_response.status_code == 200
        assert approval_response.json()["approval_id"] == approval_id

        decision_response = client.post(
            f"/approvals/{approval_id}/decision",
            json={
                "approved": False,
                "decided_by": "local_user",
                "reason": "Reject sensitive action in MVP test",
            },
        )
        assert decision_response.status_code == 200
        decision_payload = decision_response.json()
        decided = decision_payload["approval"]
        assert decided["status"] == "rejected"
        assert decided["decision"]["approved"] is False
        assert decision_payload["resume_result"]["status"] == "rejected"

        rejected_status = client.get(f"/tasks/{task_id}").json()
        assert rejected_status["status"] == "rejected"

        decided_events_response = client.get(f"/tasks/{task_id}/events")
        assert decided_events_response.status_code == 200
        assert "event: approval_decided" in decided_events_response.text
        assert "event: task_rejected" in decided_events_response.text


def test_api_risk_blocked_event_and_artifacts(tmp_path: Path) -> None:
    api_module.task_service = TaskService(runs_dir=tmp_path / "runs")

    with TestClient(api_module.app) as client:
        task_id = _create_async_risk_task(client, click="Delete account")
        status_payload = _wait_for_status(client, task_id, "blocked")

        assert status_payload["status"] == "blocked"
        assert "approvals.jsonl" in status_payload["artifacts"]
        assert "risk_report.json" in status_payload["artifacts"]

        events_response = client.get(f"/tasks/{task_id}/events")
        assert events_response.status_code == 200
        assert "event: risk_blocked" in events_response.text

        approvals_response = client.get(f"/tasks/{task_id}/approvals")
        assert approvals_response.status_code == 200
        assert approvals_response.json() == []


def _create_async_risk_task(client: TestClient, click: str) -> str:
    response = client.post(
        "/tasks/async",
        json={
            "url": "tests/fixtures/mock_site/risk_actions.html",
            "click": click,
            "expect": click,
            "planner": "deterministic",
            "workspace": "tests/fixtures/workspace",
            "reminder": "Do not perform risky actions without approval.",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "running"
    return payload["task_id"]


def _wait_for_status(
    client: TestClient,
    task_id: str,
    expected_status: str,
    timeout_seconds: float = 10.0,
) -> dict:
    deadline = time.monotonic() + timeout_seconds
    last_payload: dict = {}
    while time.monotonic() < deadline:
        response = client.get(f"/tasks/{task_id}")
        assert response.status_code == 200
        last_payload = response.json()
        if last_payload["status"] == expected_status:
            return last_payload
        if last_payload["status"] in {"succeeded", "failed", "blocked", "requires_approval"}:
            break
        time.sleep(0.1)
    raise AssertionError(f"Unexpected task status: {last_payload}")
