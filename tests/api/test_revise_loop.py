from __future__ import annotations

from fastapi.testclient import TestClient

import webscoper.api.app as api_module
from webscoper.api.task_service import TaskService


def test_api_task_supports_fake_llm_revise_loop(tmp_path) -> None:
    api_module.task_service = TaskService(runs_dir=tmp_path / "runs")
    client = TestClient(api_module.app)

    response = client.post(
        "/tasks",
        json={
            "url": "tests/fixtures/mock_site/basic.html",
            "click": "Quickstart",
            "expect": "pip install playwright",
            "planner": "deterministic",
            "reviewer": "fake_llm",
            "revise_attempts": 1,
            "workspace": "tests/fixtures/workspace",
            "reminder": "Review and revise the report against evidence.",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "succeeded"
    assert "revision_plan.json" in payload["artifacts"]
    assert "revised_report.md" in payload["artifacts"]
    assert "final_review.json" in payload["artifacts"]
    task_id = payload["task_id"]

    report_response = client.get(f"/tasks/{task_id}/artifacts/revised_report.md")
    assert report_response.status_code == 200
    assert "ev_000001" in report_response.json()["content"]

    review_response = client.get(f"/tasks/{task_id}/artifacts/final_review.json")
    assert review_response.status_code == 200
    assert '"passed": true' in review_response.json()["content"]
