from __future__ import annotations

import json
from pathlib import Path

from tests.helpers import (
    basic_task_request,
    create_async_task,
    read_jsonl,
    risk_task_request,
    wait_for_status,
)


def test_api_post_task_supports_langgraph_workflow(api_client, tmp_path: Path) -> None:
    client = api_client
    create_response = client.post(
        "/tasks",
        json=basic_task_request(),
    )

    assert create_response.status_code == 200
    payload = create_response.json()
    task_id = payload["task_id"]
    assert payload["status"] == "succeeded"
    assert "workflow_state.json" in payload["artifacts"]
    assert "events.jsonl" in payload["artifacts"]

    artifacts_response = client.get(f"/tasks/{task_id}/artifacts")
    assert artifacts_response.status_code == 200
    assert "workflow_state.json" in artifacts_response.json()["artifacts"]

    state_response = client.get(f"/tasks/{task_id}/artifacts/workflow_state.json")
    assert state_response.status_code == 200
    workflow_state = json.loads(state_response.json()["content"])
    assert workflow_state["status"] == "succeeded"
    event_names = {event["event"] for event in workflow_state["events"]}
    assert "workflow_node_started" in event_names
    assert "workflow_node_finished" in event_names

    events = read_jsonl(tmp_path / "runs" / task_id / "events.jsonl")
    event_kinds = {event["kind"] for event in events}
    assert "workflow_started" in event_kinds
    assert "workflow_finished" in event_kinds


def test_api_langgraph_approval_approved_resumes_and_finishes(
    api_client,
) -> None:
    client = api_client
    task_id = create_async_task(
        client,
        risk_task_request("Submit"),
    )
    paused = wait_for_status(client, task_id, "requires_approval")
    assert "pending.jsonl" in paused["artifacts"]
    assert "langgraph_interrupts.jsonl" in paused["artifacts"]

    approval_id = client.get(f"/tasks/{task_id}/approvals").json()[0]["approval_id"]
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

    status = wait_for_status(client, task_id, "succeeded")
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


def test_api_langgraph_approval_rejected_does_not_click(
    api_client,
    tmp_path: Path,
) -> None:
    client = api_client
    task_id = create_async_task(
        client,
        risk_task_request("Submit"),
    )
    wait_for_status(client, task_id, "requires_approval")
    approval_id = client.get(f"/tasks/{task_id}/approvals").json()[0]["approval_id"]

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
    status = wait_for_status(client, task_id, "rejected")
    assert "final_report.md" not in status["artifacts"]
    assert (tmp_path / "runs" / task_id / "final_report.md").exists() is False

    events = client.get(f"/tasks/{task_id}/events").text
    assert "event: approval_decided" in events
    assert "event: task_rejected" in events
    assert "event: langgraph_resumed" not in events


def test_api_langgraph_delete_account_is_blocked_not_interrupted(
    api_client,
) -> None:
    client = api_client
    task_id = create_async_task(
        client,
        risk_task_request("Delete account"),
    )
    status = wait_for_status(client, task_id, "blocked")

    assert status["status"] == "blocked"
    assert client.get(f"/tasks/{task_id}/approvals").json() == []
    events = client.get(f"/tasks/{task_id}/events").text
    assert "event: risk_blocked" in events
    assert "event: langgraph_interrupted" not in events
