from __future__ import annotations

from pathlib import Path

import pytest

from webscoper.browser.tool_runtime import StatefulBrowserToolRuntime
from webscoper.runtime.artifacts.evidence import EvidenceStore
from webscoper.runtime.artifacts.trace import TraceRecorder


@pytest.mark.asyncio
async def test_browser_open_and_observe_run_separately(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    await runtime.start()
    try:
        opened = await runtime.open(_fixture_url())
        observed = await runtime.observe()
    finally:
        await runtime.close()

    assert opened["status"] == "success"
    assert opened["final_url"].startswith("file://")
    assert observed["status"] == "success"
    assert observed["observation_id"]
    assert observed["accessibility_summary"]
    assert observed["screenshot_evidence_id"]
    assert (tmp_path / "run" / "observation.json").is_file()


@pytest.mark.asyncio
async def test_scroll_wait_type_select_and_screenshot_on_local_fixture(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    await runtime.start()
    try:
        await runtime.open(_fixture_url())
        scroll = await runtime.scroll(direction="down", amount="large")
        wait = await runtime.wait(condition="readiness", timeout_ms=1000)
        typed = await runtime.type_text(target_hint="Search query", text="mock query")
        selected = await runtime.select_option(
            target_hint="Safe category",
            option_text="Runtime",
        )
        screenshot = await runtime.screenshot(reason="test")
    finally:
        await runtime.close()

    assert scroll["status"] == "success"
    assert scroll["scroll_position_after"]["y"] >= scroll["scroll_position_before"]["y"]
    assert wait["status"] in {"success", "timeout"}
    assert typed["status"] == "success"
    assert typed["diff"]["interactive_elements_count_after"] >= 1
    assert selected["status"] == "success"
    assert screenshot["screenshot_evidence_id"]


@pytest.mark.asyncio
async def test_browser_type_blocks_sensitive_fields(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    await runtime.start()
    try:
        await runtime.open(_fixture_url())
        output = await runtime.type_text(target_hint="Password", text="secret-token-123")
    finally:
        await runtime.close()

    assert output["status"] == "blocked"
    assert output["error_type"] == "SENSITIVE_INPUT_BLOCKED"


@pytest.mark.asyncio
async def test_v2_runtime_events_include_executor_verifier_and_spans(tmp_path: Path) -> None:
    events = []
    runtime = _runtime(
        tmp_path,
        event_sink=lambda kind, message, payload=None: events.append((kind, payload or {})),
    )
    await runtime.start()
    try:
        await runtime.open(_fixture_url())
        await runtime.click(
            target_hint="Noop button",
            expected_effect={"type": "none"},
        )
    finally:
        await runtime.close()

    kinds = [kind for kind, _payload in events]
    assert "executor_started" in kinds
    assert "executor_finished" in kinds
    assert "verifier_started" in kinds
    assert "verifier_finished" in kinds
    assert any(payload.get("span_id") for _kind, payload in events)


def _runtime(tmp_path: Path, event_sink=None) -> StatefulBrowserToolRuntime:
    run_dir = tmp_path / "run"
    return StatefulBrowserToolRuntime(
        trace_recorder=TraceRecorder(run_dir=run_dir, run_id="browser_tools_v2"),
        event_sink=event_sink,
        evidence_store=EvidenceStore(run_dir / "evidence.jsonl"),
    )


def _fixture_url() -> str:
    return Path("tests/fixtures/mock_site/browser_tools_v2.html").resolve().as_uri()
