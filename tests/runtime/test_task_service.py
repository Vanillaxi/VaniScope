from __future__ import annotations

from pathlib import Path

import pytest

from webscoper.api.schemas import TaskCreateRequest
from webscoper.api.task_service import TaskService


def test_task_service_runs_fake_llm_task(tmp_path: Path) -> None:
    service = TaskService(runs_dir=tmp_path / "runs")

    response = service.create_and_run_task(
        TaskCreateRequest(
            url="tests/fixtures/mock_site/basic.html",
            click="Quickstart",
            expect="pip install playwright",
            planner="fake_llm",
            workspace="tests/fixtures/workspace",
            reminder="This is a test runtime reminder.",
        )
    )

    assert response.status == "succeeded"
    assert "final_report.md" in response.artifacts
    assert "review_summary.md" in response.artifacts

    status = service.get_task_status(response.task_id)
    assert status.status == "succeeded"
    assert status.run_dir == response.run_dir


def test_task_service_rejects_disallowed_artifact(tmp_path: Path) -> None:
    service = TaskService(runs_dir=tmp_path / "runs")
    run_dir = tmp_path / "runs" / "task_test"
    run_dir.mkdir(parents=True)

    with pytest.raises(ValueError, match="not allowed"):
        service.read_artifact("task_test", "../../../.env")


def test_task_service_returns_not_found_status(tmp_path: Path) -> None:
    service = TaskService(runs_dir=tmp_path / "runs")

    status = service.get_task_status("missing")

    assert status.status == "not_found"
