from __future__ import annotations

from fastapi.testclient import TestClient

from webscoper.api.app import app


def test_api_health() -> None:
    client = TestClient(app)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "vaniscope-api",
    }
