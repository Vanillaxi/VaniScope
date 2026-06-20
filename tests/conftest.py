from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import webscoper.api.app as api_module
from webscoper.api.task_service import TaskService


@pytest.fixture
def api_client(tmp_path, monkeypatch):
    monkeypatch.setenv("VANISCOPE_LLM_CONFIG", str(tmp_path / "llm.local.toml"))
    api_module.task_service = TaskService(
        runs_dir=tmp_path / "runs",
        runtime_config_path=tmp_path / "runtime.local.toml",
    )
    with TestClient(api_module.app) as client:
        yield client
