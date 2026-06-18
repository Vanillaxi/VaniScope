from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient


def mock_site_path(name: str) -> str:
    return f"tests/fixtures/mock_site/{name}"


def workspace_path() -> str:
    return "tests/fixtures/workspace"


def basic_task_request(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "url": mock_site_path("basic.html"),
        "click": "Quickstart",
        "expect": "pip install playwright",
        "planner": "deterministic",
        "workspace": workspace_path(),
        "reminder": "This is a test runtime reminder.",
    }
    payload.update(overrides)
    return payload


def risk_task_request(click: str, **overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "url": mock_site_path("risk_actions.html"),
        "click": click,
        "expect": "Submitted successfully" if click == "Submit" else click,
        "planner": "deterministic",
        "workspace": workspace_path(),
        "reminder": "Do not perform sensitive actions without approval.",
    }
    payload.update(overrides)
    return payload


def create_async_task(client: TestClient, payload: dict[str, Any]) -> str:
    response = client.post("/tasks/async", json=payload)
    assert response.status_code == 200
    created = response.json()
    assert created["status"] == "running"
    return str(created["task_id"])


def wait_for_status(
    client: TestClient,
    task_id: str,
    expected_status: str,
    timeout_seconds: float = 10.0,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    last_payload: dict[str, Any] = {}
    while time.monotonic() < deadline:
        response = client.get(f"/tasks/{task_id}")
        assert response.status_code == 200
        last_payload = response.json()
        if last_payload["status"] == expected_status:
            return last_payload
        if last_payload["status"] in {
            "succeeded",
            "failed",
            "blocked",
            "rejected",
        }:
            break
        time.sleep(0.1)
    raise AssertionError(f"Unexpected task status: {last_payload}")


def wait_for_terminal_status(
    client: TestClient,
    task_id: str,
    timeout_seconds: float = 10.0,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    last_payload: dict[str, Any] = {}
    while time.monotonic() < deadline:
        response = client.get(f"/tasks/{task_id}")
        assert response.status_code == 200
        last_payload = response.json()
        if last_payload["status"] in {"succeeded", "failed"}:
            return last_payload
        time.sleep(0.1)
    raise AssertionError(f"Task did not finish before timeout: {last_payload}")


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def assert_artifact_exists(run_dir: Path, artifact_name: str) -> Path:
    path = run_dir / artifact_name
    assert path.is_file()
    return path
