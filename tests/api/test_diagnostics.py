from __future__ import annotations


def test_api_diagnostics_returns_local_runtime_status(api_client) -> None:
    response = api_client.get("/diagnostics")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["service"] == "vaniscope-api"
    assert payload["runtime_backend"] == "langgraph"
    assert payload["artifact_directory"]["writable"] is True
    assert payload["llm"]["mode"] == "fake"
    assert payload["llm"]["real_llm_enabled_by_default"] is False
    assert payload["llm"]["api_key_required_for_default"] is False
    assert {
        skill["skill_id"] for skill in payload["registered_skills"]
    } == {"docs_research", "github_issue_research"}
    assert "playwright_importable" in payload["browser"]
    assert payload["config"]["sensitive_values_redacted"] is True
    assert "VANISCOPE_LLM_API_KEY" not in str(payload)
