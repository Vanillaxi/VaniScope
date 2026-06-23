from __future__ import annotations

from pathlib import Path

from tests.helpers import create_async_task, mock_site_path, read_json, read_jsonl, wait_for_status, wait_for_terminal_status


def test_auto_explore_extracts_without_forcing_click(api_client) -> None:
    task_id = create_async_task(
        api_client,
        {
            "url": mock_site_path("basic.html"),
            "goal": "Summarize the visible page information.",
            "mode": "auto_explore",
            "planner": "fake_llm",
            "workspace": "tests/fixtures/workspace",
            "max_steps": 5,
        },
    )

    status = wait_for_terminal_status(api_client, task_id)
    assert status["status"] == "succeeded"
    tool_audit = read_jsonl(Path(status["run_dir"]) / "tool_audit.jsonl")
    tools = [row["tool_name"] for row in tool_audit]
    assert "browser_extract" in tools


def test_auto_explore_executes_safe_click_intent(api_client) -> None:
    task_id = create_async_task(
        api_client,
        {
            "url": mock_site_path("basic.html"),
            "goal": "Click Quickstart, then summarize the installation evidence.",
            "mode": "auto_explore",
            "planner": "fake_llm",
            "workspace": "tests/fixtures/workspace",
            "max_steps": 6,
        },
    )

    status = wait_for_terminal_status(api_client, task_id)
    assert status["status"] == "succeeded"
    tool_audit = read_jsonl(Path(status["run_dir"]) / "tool_audit.jsonl")
    assert "browser_click" in [row["tool_name"] for row in tool_audit]


def test_auto_explore_invalid_action_fails_safely(api_client) -> None:
    task_id = create_async_task(
        api_client,
        {
            "url": mock_site_path("basic.html"),
            "goal": "invalid_action",
            "mode": "auto_explore",
            "planner": "fake_llm",
            "workspace": "tests/fixtures/workspace",
            "max_steps": 4,
        },
    )

    status = wait_for_status(api_client, task_id, "failed")
    assert status["error"]
    run_dir = Path(status["run_dir"])
    transcript = read_jsonl(Path(status["run_dir"]) / "transcript.jsonl")
    assert any(row["event_type"] == "auto_explore_validation_failed" for row in transcript)
    validation = read_json(run_dir / "action_validation.json")
    assert validation["repair_attempt_count"] == 1
    assert validation["validation_errors"]
    assert len(read_jsonl(run_dir / "llm_calls.jsonl")) == 2


def test_auto_explore_selector_output_is_rejected(api_client) -> None:
    task_id = create_async_task(
        api_client,
        {
            "url": mock_site_path("basic.html"),
            "goal": "selector_action",
            "mode": "auto_explore",
            "planner": "fake_llm",
            "workspace": "tests/fixtures/workspace",
            "max_steps": 4,
        },
    )

    status = wait_for_status(api_client, task_id, "failed")
    validation = read_json(Path(status["run_dir"]) / "action_validation.json")
    assert "forbidden raw automation pattern" in str(validation["validation_errors"])


def test_auto_explore_risky_action_is_blocked(api_client) -> None:
    task_id = create_async_task(
        api_client,
        {
            "url": mock_site_path("risk_actions.html"),
            "goal": "Delete the account.",
            "mode": "auto_explore",
            "planner": "fake_llm",
            "workspace": "tests/fixtures/workspace",
            "max_steps": 4,
        },
    )

    status = wait_for_status(api_client, task_id, "blocked")
    assert status["status"] == "blocked"
    risk_report = Path(status["run_dir"]) / "risk_report.json"
    assert risk_report.exists()
