from __future__ import annotations

import time
from pathlib import Path

from fastapi.testclient import TestClient

import webscoper.api.app as api_module
from webscoper.api.task_service import TaskService


def test_api_langgraph_approval_approved_resumes_and_finishes(
    tmp_path: Path,
) -> None:
    api_module.task_service = TaskService(runs_dir=tmp_path / "runs")

    with TestClient(api_module.app) as client:
        task_id = _create_langgraph_task(client, click="Submit")
        paused = _wait_for_status(client, task_id, "requires_approval")
        assert "pending.jsonl" in paused["artifacts"]
        assert "langgraph_interrupts.jsonl" in paused["artifacts"]

        approval_id = client.get(f"/tasks/{task_id}/approvals").json()[0][
            "approval_id"
        ]
        decision_response = client.post(
            f"/approvals/{approval_id}/decision",
            json={
                "approved": True,
                "decided_by": "local_user",
                "reason": "Approve local mock submit action.",
            },
        )

        assert decision_response.status_code == 200
        decision = decision_response.json()
        assert decision["resume_result"]["resumed"] is True
        assert decision["resume_result"]["status"] == "succeeded"

        status = _wait_for_status(client, task_id, "succeeded")
        assert "workflow_state.json" in status["artifacts"]
        assert "final_report.md" in status["artifacts"]
        assert "review.json" in status["artifacts"]
        assert "compact_context.json" in status["artifacts"]

        report = client.get(f"/tasks/{task_id}/artifacts/final_report.md").json()
        assert "Submitted successfully" in report["content"]

        events = client.get(f"/tasks/{task_id}/events").text
        assert "event: approval_required" in events
        assert "event: langgraph_interrupted" in events
        assert "event: task_paused" in events
        assert "event: approval_decided" in events
        assert "event: langgraph_resumed" in events
        assert "event: task_resumed" in events
        assert "event: tool_call_finished" in events
        assert "event: task_finished" in events


def test_api_langgraph_approval_rejected_does_not_click(tmp_path: Path) -> None:
    api_module.task_service = TaskService(runs_dir=tmp_path / "runs")

    with TestClient(api_module.app) as client:
        task_id = _create_langgraph_task(client, click="Submit")
        _wait_for_status(client, task_id, "requires_approval")
        approval_id = client.get(f"/tasks/{task_id}/approvals").json()[0][
            "approval_id"
        ]

        decision_response = client.post(
            f"/approvals/{approval_id}/decision",
            json={
                "approved": False,
                "decided_by": "local_user",
                "reason": "Reject local mock submit action.",
            },
        )

        assert decision_response.status_code == 200
        assert decision_response.json()["resume_result"]["status"] == "rejected"
        status = _wait_for_status(client, task_id, "rejected")
        assert "final_report.md" not in status["artifacts"]
        assert (tmp_path / "runs" / task_id / "final_report.md").exists() is False

        events = client.get(f"/tasks/{task_id}/events").text
        assert "event: approval_decided" in events
        assert "event: task_rejected" in events
        assert "event: langgraph_resumed" not in events


def test_api_langgraph_delete_account_is_blocked_not_interrupted(
    tmp_path: Path,
) -> None:
    api_module.task_service = TaskService(runs_dir=tmp_path / "runs")

    with TestClient(api_module.app) as client:
        task_id = _create_langgraph_task(client, click="Delete account")
        status = _wait_for_status(client, task_id, "blocked")

        assert status["status"] == "blocked"
        assert client.get(f"/tasks/{task_id}/approvals").json() == []
        events = client.get(f"/tasks/{task_id}/events").text
        assert "event: risk_blocked" in events
        assert "event: langgraph_interrupted" not in events


def _create_langgraph_task(client: TestClient, click: str) -> str:
    expect = "Submitted successfully" if click == "Submit" else click
    response = client.post(
        "/tasks/async",
        json={
            "url": "tests/fixtures/mock_site/risk_actions.html",
            "click": click,
            "expect": expect,
            "planner": "deterministic",
            "workflow": "langgraph",
            "workspace": "tests/fixtures/workspace",
            "reminder": "Do not perform sensitive actions without approval.",
        },
    )
    assert response.status_code == 200
    return response.json()["task_id"]


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
        if last_payload["status"] in {"succeeded", "failed", "blocked", "rejected"}:
            break
        time.sleep(0.1)
    raise AssertionError(f"Unexpected task status: {last_payload}")
