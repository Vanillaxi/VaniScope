from __future__ import annotations

from pathlib import Path

from webscoper.api.task_service import TaskService
from tests.helpers import create_async_task, risk_task_request, wait_for_status


def test_approval_approved_resumes_and_finishes_task(api_client) -> None:
    client = api_client
    task_id = create_async_task(client, risk_task_request("Submit"))
    paused = wait_for_status(client, task_id, "requires_approval")
    assert "pending.jsonl" in paused["artifacts"]

    approvals = client.get(f"/tasks/{task_id}/approvals").json()
    approval_id = approvals[0]["approval_id"]

    decision_response = client.post(
        f"/approvals/{approval_id}/decision",
        json={
            "approved": True,
            "decided_by": "local_user",
            "reason": "Approve local mock submit action.",
        },
    )
    assert decision_response.status_code == 200
    decision_payload = decision_response.json()
    assert decision_payload["approval"]["status"] == "approved"
    assert decision_payload["resume_result"]["resumed"] is True
    assert decision_payload["resume_result"]["status"] == "succeeded"

    status_payload = wait_for_status(client, task_id, "succeeded")
    assert "final_report.md" in status_payload["artifacts"]
    assert "review.json" in status_payload["artifacts"]

    report_response = client.get(f"/tasks/{task_id}/artifacts/final_report.md")
    assert report_response.status_code == 200
    assert "Submitted successfully" in report_response.json()["content"]

    events_response = client.get(f"/tasks/{task_id}/events")
    assert events_response.status_code == 200
    body = events_response.text
    assert "event: approval_required" in body
    assert "event: task_paused" in body
    assert "event: approval_decided" in body
    assert "event: task_resumed" in body
    assert "event: task_finished" in body


def test_approved_pending_tool_call_cannot_resume_twice(api_client) -> None:
    client = api_client
    task_id = create_async_task(client, risk_task_request("Submit"))
    wait_for_status(client, task_id, "requires_approval")
    approval_id = client.get(f"/tasks/{task_id}/approvals").json()[0]["approval_id"]

    first = client.post(
        f"/approvals/{approval_id}/decision",
        json={"approved": True, "decided_by": "local_user"},
    )
    assert first.status_code == 200
    assert first.json()["resume_result"]["resumed"] is True

    # The public API rejects duplicate decisions before a second resume is possible.
    second = client.post(
        f"/approvals/{approval_id}/decision",
        json={"approved": True, "decided_by": "local_user"},
    )
    assert second.status_code == 400


def test_approved_without_pending_returns_not_resumed(tmp_path: Path) -> None:
    service = TaskService(runs_dir=tmp_path / "runs")
    approval = service.approval_store.create_request(
        task_id="task_missing_pending",
        reason="Manual approval.",
        risk_level="sensitive",
    )
    (tmp_path / "runs" / "task_missing_pending").mkdir(parents=True)

    response = service.decide_approval(
        approval.approval_id,
        approved=True,
        decided_by="local_user",
    )

    assert response.resume_result is not None
    assert response.resume_result.resumed is False
    assert response.resume_result.status == "failed"
