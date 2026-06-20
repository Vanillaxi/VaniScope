from __future__ import annotations

import json
from pathlib import Path

import pytest

from webscoper.browser.tool_runtime import StatefulBrowserToolRuntime
from webscoper.runtime.artifacts.trace import TraceRecorder
from webscoper.runtime.artifacts.transcript import TranscriptStore
from webscoper.schemas.browser import ActionContract, ExpectedEffect


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("fixture_name", "expected_status"),
    [
        ("early_button_hydration.html", "succeeded"),
    ],
)
async def test_browser_runtime_recovers_click_failures(
    tmp_path: Path,
    fixture_name: str,
    expected_status: str,
) -> None:
    run_dir = tmp_path / fixture_name.removesuffix(".html")
    events: list[tuple[str, dict]] = []
    recorder = TraceRecorder(run_dir=run_dir, run_id=fixture_name)
    transcript = TranscriptStore(run_dir=run_dir, run_id=fixture_name)
    runtime = StatefulBrowserToolRuntime(
        trace_recorder=recorder,
        transcript_store=transcript,
        event_sink=lambda kind, message, payload=None: events.append((kind, payload or {})),
    )

    await runtime.start()
    try:
        await runtime.open_observe(
            Path(f"tests/fixtures/mock_site/{fixture_name}").resolve().as_uri()
        )
        output = await runtime.click_intent(_quickstart_contract())
    finally:
        await runtime.close()

    assert "pip install playwright" in output["observation"]["visible_text_summary"]
    attempts = _read_jsonl(run_dir / "recovery.jsonl")
    assert any(attempt["status"] == expected_status for attempt in attempts)
    event_kinds = [kind for kind, _ in events]
    assert "recovery_started" in event_kinds
    assert "recovery_succeeded" in event_kinds
    transcript_events = [
        item["event_type"] for item in _read_jsonl(transcript.transcript_path)
    ]
    assert "recovery_succeeded" in transcript_events


@pytest.mark.asyncio
async def test_disabled_target_is_not_force_clicked(tmp_path: Path) -> None:
    page_url = _write_html(
        tmp_path,
        "disabled_button.html",
        """
        <!doctype html>
        <html>
        <body>
          <h1>VaniScope Disabled Mock</h1>
          <button id="submit" disabled>Submit</button>
          <button id="open-docs" disabled>Open docs</button>
        </body>
        </html>
        """,
    )
    run_dir = tmp_path / "disabled"
    recorder = TraceRecorder(run_dir=run_dir, run_id="disabled")
    runtime = StatefulBrowserToolRuntime(trace_recorder=recorder)

    await runtime.start()
    try:
        await runtime.open_observe(page_url)
        await runtime.click_intent(
            ActionContract(
                action_type="click",
                intent="Click Submit",
                target_hint="Submit",
                preferred_roles=["button"],
                expected_effect=ExpectedEffect(type="none"),
                risk_level="read_only",
            )
        )
    finally:
        await runtime.close()

    trace_steps = _read_jsonl(recorder.trace_path)
    assert any(
        step.get("error_type") == "TARGET_DISABLED_PENDING_HYDRATION"
        for step in trace_steps
    )
    attempts = _read_jsonl(run_dir / "recovery.jsonl")
    assert attempts[-1]["status"] == "failed"


def _quickstart_contract() -> ActionContract:
    return ActionContract(
        action_type="click",
        intent="Click Quickstart",
        target_hint="Quickstart",
        preferred_roles=["button", "link"],
        expected_effect=ExpectedEffect(
            type="content_appears",
            value="pip install playwright",
        ),
        risk_level="read_only",
    )


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _write_html(tmp_path: Path, name: str, content: str) -> str:
    path = tmp_path / name
    path.write_text(content, encoding="utf-8")
    return path.resolve().as_uri()
