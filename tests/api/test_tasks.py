from __future__ import annotations

def test_api_artifact_traversal_rejected(api_client) -> None:
    client = api_client
    response = client.get("/tasks/missing/artifacts/..%2F..%2F.env")

    assert response.status_code in {400, 404}
