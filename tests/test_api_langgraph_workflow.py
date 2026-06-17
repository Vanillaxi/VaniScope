from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

import webscoper.api.app as api_module
from webscoper.api.task_service import TaskService


def test_api_post_task_supports_langgraph_workflow(tmp_path: Path) -> None:
    api_module.task_service = TaskService(runs_dir=tmp_path / "runs")
    client = TestClient(api_module.app)

    create_response = client.post(
        "/tasks",
        json={
            "url": "tests/fixtures/mock_site/basic.html",
            "click": "Quickstart",
            "expect": "pip install playwright",
            "planner": "deterministic",
            "workflow": "langgraph",
            "workspace": "tests/fixtures/workspace",
            "reminder": "This is a test runtime reminder.",
        },
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

    events = [
        json.loads(line)
        for line in (tmp_path / "runs" / task_id / "events.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    event_kinds = {event["kind"] for event in events}
    assert "workflow_started" in event_kinds
    assert "workflow_finished" in event_kinds
