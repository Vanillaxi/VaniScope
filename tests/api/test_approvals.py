from __future__ import annotations

from tests.helpers import create_async_task, risk_task_request, wait_for_status


def test_api_lists_and_decides_task_approval(api_client) -> None:
    client = api_client
    task_id = create_async_task(client, risk_task_request("Submit", expect="Submit"))
    status_payload = wait_for_status(client, task_id, "requires_approval")

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


def test_api_risk_blocked_event_and_artifacts(api_client) -> None:
    client = api_client
    task_id = create_async_task(client, risk_task_request("Delete account"))
    status_payload = wait_for_status(client, task_id, "blocked")

    assert status_payload["status"] == "blocked"
    assert "approvals.jsonl" in status_payload["artifacts"]
    assert "risk_report.json" in status_payload["artifacts"]

    events_response = client.get(f"/tasks/{task_id}/events")
    assert events_response.status_code == 200
    assert "event: risk_blocked" in events_response.text

    approvals_response = client.get(f"/tasks/{task_id}/approvals")
    assert approvals_response.status_code == 200
    assert approvals_response.json() == []
