from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import webscoper.api.app as api_module
from webscoper.api.task_service import TaskService


@pytest.fixture
def api_client(tmp_path):
    api_module.task_service = TaskService(runs_dir=tmp_path / "runs")
    with TestClient(api_module.app) as client:
        yield client
