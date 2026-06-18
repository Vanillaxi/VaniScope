from __future__ import annotations

from pathlib import Path

import pytest

from webscoper.api.schemas import TaskCreateRequest
from webscoper.api.task_service import ARTIFACT_ALLOWLIST, TaskService


def test_api_artifact_allowlist_includes_compaction_artifacts(tmp_path: Path) -> None:
    service = TaskService(runs_dir=tmp_path / "runs")
    response = service.create_and_run_task(
        TaskCreateRequest(
            url="tests/fixtures/mock_site/basic.html",
            click="Quickstart",
            expect="pip install playwright",
            planner="deterministic",
            workspace="tests/fixtures/workspace",
        )
    )

    assert "compact_context.json" in ARTIFACT_ALLOWLIST
    assert "compact_summary.md" in ARTIFACT_ALLOWLIST
    assert "compact_context.json" in response.artifacts
    assert "compact_summary.md" in response.artifacts
    content = service.read_artifact(response.task_id, "compact_summary.md")
    assert "# Compact Runtime Context" in content.content


def test_api_artifact_traversal_still_rejected(tmp_path: Path) -> None:
    service = TaskService(runs_dir=tmp_path / "runs")
    run_dir = tmp_path / "runs" / "task_test"
    run_dir.mkdir(parents=True)

    with pytest.raises(ValueError, match="not allowed"):
        service.read_artifact("task_test", "../compact_summary.md")
