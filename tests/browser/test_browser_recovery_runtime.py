from __future__ import annotations

import json
from pathlib import Path

import pytest

from webscoper.runtime.browser_runtime import BrowserRuntime
from webscoper.runtime.trace import TraceRecorder
from webscoper.runtime.transcript import TranscriptStore
from webscoper.schemas.action import ActionContract, ExpectedEffect


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("fixture_name", "expected_status"),
    [
        ("lazy_button.html", "succeeded"),
        ("no_effect_click.html", "succeeded"),
        ("modal_overlay.html", "succeeded"),
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
    runtime = BrowserRuntime(
        trace_recorder=recorder,
        transcript_store=transcript,
        event_sink=lambda kind, message, payload=None: events.append((kind, payload or {})),
    )

    observation = await runtime.open_click_and_observe(
        Path(f"tests/fixtures/mock_site/{fixture_name}").resolve().as_uri(),
        _quickstart_contract(),
    )

    assert "pip install playwright" in observation.visible_text_summary
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
    run_dir = tmp_path / "disabled"
    recorder = TraceRecorder(run_dir=run_dir, run_id="disabled")
    runtime = BrowserRuntime(trace_recorder=recorder)

    await runtime.open_click_and_observe(
        Path("tests/fixtures/mock_site/disabled_button.html").resolve().as_uri(),
        ActionContract(
            action_type="click",
            intent="Click Submit",
            target_hint="Submit",
            preferred_roles=["button"],
            expected_effect=ExpectedEffect(type="none"),
            risk_level="read_only",
        ),
    )

    trace_steps = _read_jsonl(recorder.trace_path)
    assert any(step.get("error_type") == "TARGET_DISABLED" for step in trace_steps)
    attempts = _read_jsonl(run_dir / "recovery.jsonl")
    assert attempts[-1]["strategy"] == "abort_as_failed"
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
