from __future__ import annotations

import json
from pathlib import Path

import pytest

from webscoper.runtime.execution import WebAgentExecutionHandler
from webscoper.runtime.reminders import RuntimeReminderStore
from webscoper.schemas.task import TaskSpec


@pytest.mark.asyncio
async def test_execution_handler_persists_prompt_context(
    tmp_path: Path,
) -> None:
    workspace = Path("tests/fixtures/workspace")
    reminders = RuntimeReminderStore()
    reminders.add("This is a test runtime reminder.", level="warning", source="test")
    task = TaskSpec(
        task_id="prompt_integration",
        raw_input="Open local basic mock.",
        target_url=Path("tests/fixtures/mock_site/basic.html").resolve().as_uri(),
        tags=["prompt", "integration"],
    )
    handler = WebAgentExecutionHandler(
        output_root=tmp_path,
        workspace=workspace,
        runtime_reminders=reminders,
    )

    await handler.run(task)

    context = handler.last_context
    assert context is not None
    prompt_preview_path = context.run_dir / "prompt_preview.md"
    prompt_context_path = context.run_dir / "prompt_context.json"
    transcript_path = context.transcript_store.transcript_path

    assert prompt_preview_path.exists()
    assert prompt_context_path.exists()
    assert transcript_path.exists()
    assert context.trace_recorder.trace_path.exists()

    prompt_preview = prompt_preview_path.read_text(encoding="utf-8")
    prompt_context = json.loads(prompt_context_path.read_text(encoding="utf-8"))
    event_types = [
        json.loads(line)["event_type"]
        for line in transcript_path.read_text(encoding="utf-8").splitlines()
    ]

    assert "VaniScope" in prompt_preview
    assert "Prefer official documentation" in prompt_preview
    assert "system-reminder" in prompt_preview
    assert prompt_context["loaded_agents_md_paths"]
    assert "agents_md_loaded" in event_types
    assert "prompt_built" in event_types
    assert "execution_completed" in event_types
