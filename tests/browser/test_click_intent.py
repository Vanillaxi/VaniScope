from __future__ import annotations

import json
from pathlib import Path

import pytest

from webscoper.runtime.browser_runtime import BrowserRuntime
from webscoper.runtime.artifacts.trace import TraceRecorder
from webscoper.schemas.action import ActionContract, ExpectedEffect


@pytest.mark.asyncio
async def test_click_intent_runtime_reveals_expected_content(tmp_path: Path) -> None:
    run_dir = tmp_path / "run_click"
    recorder = TraceRecorder(run_dir=run_dir, run_id="run_click")
    runtime = BrowserRuntime(trace_recorder=recorder)
    url = Path("tests/fixtures/mock_site/basic.html").resolve().as_uri()
    contract = ActionContract(
        action_type="click",
        intent="Click Quickstart",
        target_hint="Quickstart",
        preferred_roles=["button", "link"],
        preconditions=["target_visible", "target_enabled"],
        expected_effect=ExpectedEffect(
            type="content_appears",
            value="pip install playwright",
        ),
        risk_level="read_only",
    )

    observation = await runtime.open_click_and_observe(url, contract)

    assert "pip install playwright" in observation.visible_text_summary
    assert recorder.trace_path.exists()
    lines = recorder.trace_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) >= 3
    action_types = [json.loads(line)["action_type"] for line in lines]
    assert "browser_click_intent" in action_types
    assert "effect_verify" in action_types
