from __future__ import annotations

from pathlib import Path

from tests.helpers import basic_task_request, read_json, read_jsonl


def test_api_task_graph_returns_runtime_chain_and_writes_artifact(api_client) -> None:
    create_response = api_client.post("/tasks", json=basic_task_request())
    assert create_response.status_code == 200
    created = create_response.json()
    task_id = created["task_id"]
    run_dir = Path(created["run_dir"])

    response = api_client.get(f"/tasks/{task_id}/graph")

    assert response.status_code == 200
    payload = response.json()
    assert payload["task_id"] == task_id
    assert payload["fallback"] is False
    assert payload["nodes"]
    assert payload["edges"]
    assert len({node["id"] for node in payload["nodes"]}) == len(payload["nodes"])
    assert any(node["type"] == "browser" for node in payload["nodes"])
    assert any(node["type"] == "readiness" for node in payload["nodes"])
    assert any(node["type"] == "evidence" for node in payload["nodes"])

    graph_path = run_dir / "graph.json"
    assert graph_path.is_file()
    assert read_json(graph_path)["task_id"] == task_id


def test_runtime_screenshot_evidence_and_events_are_first_class(api_client) -> None:
    create_response = api_client.post("/tasks", json=basic_task_request())
    assert create_response.status_code == 200
    created = create_response.json()
    run_dir = Path(created["run_dir"])

    evidence = read_jsonl(run_dir / "evidence.jsonl")
    screenshot_items = [
        item
        for item in evidence
        if item["kind"]
        in {
            "page_screenshot",
            "before_action_screenshot",
            "after_action_screenshot",
            "failure_screenshot",
        }
    ]
    assert screenshot_items
    assert all(item["evidence_id"] for item in screenshot_items)
    assert all(item["screenshot_path"] for item in screenshot_items)
    assert all(item["step_id"] for item in screenshot_items)
    assert all(item["tool_name"] for item in screenshot_items)

    events = read_jsonl(run_dir / "events.jsonl")
    kinds = {event["kind"] for event in events}
    assert "browser_open_started" in kinds
    assert "readiness_sampled" in kinds
    assert "effect_verification_finished" in kinds
    assert "screenshot_evidence_added" in kinds

    readiness_event = next(event for event in events if event["kind"] == "readiness_sampled")
    for key in [
        "dom_complete",
        "url_stable",
        "title_stable",
        "text_stable",
        "interactive_elements_stable",
        "spinner_absent",
        "skeleton_absent",
        "overlay_absent",
        "layout_stable",
        "soft_network_quiet",
        "confidence",
        "elapsed_ms",
    ]:
        assert key in readiness_event["payload"]
