from __future__ import annotations

# From test_agents_md_loader.py
from pathlib import Path

from webscoper.runtime.prompt.agents_md import AgentsMdLoader


def test_agents_md_loader_loads_workspace_instructions() -> None:
    workspace = Path("tests/fixtures/workspace")

    instructions = AgentsMdLoader(include_global=False).load(workspace)

    assert len(instructions) >= 1
    assert "Prefer official documentation" in instructions[0].content
    assert instructions[0].source_path.endswith("AGENTS.md")

# From test_prompt_builder.py
from webscoper.runtime.prompt.builder import DynamicPromptBuilder
from webscoper.schemas.runtime import (
    RuntimeState,
    TraceContext,
    WebAgentContextSnapshot,
)
from webscoper.schemas.runtime import AgentsMdInstruction, RuntimeReminder
from webscoper.schemas.task import TaskSpec
from webscoper.schemas.runtime import VersionContext
from webscoper.tools.registry import create_default_tool_registry


def test_dynamic_prompt_builder_includes_task_tools_agents_and_reminders() -> None:
    task = TaskSpec(
        task_id="prompt_test",
        raw_input="Open local mock page.",
        target_url="file:///tmp/basic.html",
        tags=["prompt"],
    )
    context = WebAgentContextSnapshot(
        task=task,
        trace=TraceContext(
            run_id="run_prompt",
            run_dir="/tmp/run_prompt",
            trace_path="/tmp/run_prompt/trace.jsonl",
            transcript_path="/tmp/run_prompt/transcript.jsonl",
        ),
        version=VersionContext(),
        budget=task.budget,
        safety=task.safety,
        state=RuntimeState(status="context_built"),
    )

    result = DynamicPromptBuilder(create_default_tool_registry()).build(
        context,
        agents_md_instructions=[
            AgentsMdInstruction(
                source_path="/tmp/AGENTS.md",
                content="- Prefer official documentation.",
            )
        ],
        runtime_reminders=[
            RuntimeReminder(
                message="This is a test runtime reminder.",
                level="warning",
                source="test",
            )
        ],
    )

    assert "You are VaniScope" in result.prompt_text
    assert "prompt_test" in result.prompt_text
    assert "Core Tools" in result.prompt_text
    assert "Lazy Tools" in result.prompt_text
    assert "AGENTS.md" in result.prompt_text
    assert "system-reminder" in result.prompt_text
    assert "Do not bypass login" in result.prompt_text
    assert result.core_tool_ids
    assert result.lazy_tool_ids

# From test_prompt_builder_compacted_context.py
from webscoper.runtime.prompt.builder import DynamicPromptBuilder
from webscoper.schemas.artifact import (
    CompactedBrowserState,
    CompactedEvidenceRef,
    CompactedRecoveryState,
    CompactedRiskState,
    CompactedStep,
    ContextPack,
)
from webscoper.schemas.runtime import RuntimeState, TraceContext, WebAgentContextSnapshot
from webscoper.schemas.task import TaskSpec
from webscoper.schemas.runtime import VersionContext
from webscoper.tools.registry import create_default_tool_registry


def test_prompt_builder_injects_compacted_context() -> None:
    context = _snapshot()
    pack = ContextPack(
        task_id="prompt_test",
        task_goal="Click Quickstart",
        current_state=CompactedBrowserState(
            current_url="file:///tmp/basic.html",
            current_title="Basic",
            visible_text_preview="Quickstart Install pip install playwright",
        ),
        key_steps=[
            CompactedStep(
                step_id="step_001",
                kind="browser_open_observe",
                summary="Opened page",
                status="success",
            )
        ],
        recent_steps=[],
        evidence_refs=[
            CompactedEvidenceRef(
                evidence_id="ev_000001",
                kind="page_observation",
                source_url="file:///tmp/basic.html",
                page_title="Basic",
                text_preview="pip install playwright",
            )
        ],
        recovery_state=CompactedRecoveryState(total_attempts=1, recovered_count=1),
        risk_state=CompactedRiskState(),
        next_action_hint="Continue from current browser state.",
    )

    result = DynamicPromptBuilder(create_default_tool_registry()).build(
        context,
        context_pack=pack,
    )

    assert "# Compacted Runtime Context" in result.prompt_text
    assert "ev_000001" in result.prompt_text
    assert "recovered_count: 1" in result.prompt_text
    assert result.compact_context_metadata is not None
    assert "compacted_context" in result.sections


def test_prompt_builder_without_compacted_context_keeps_old_shape() -> None:
    result = DynamicPromptBuilder(create_default_tool_registry()).build(_snapshot())

    assert "# Compacted Runtime Context" not in result.prompt_text
    assert result.compact_context_metadata is None
    assert "compacted_context" not in result.sections


def _snapshot() -> WebAgentContextSnapshot:
    task = TaskSpec(
        task_id="prompt_test",
        raw_input="Open local mock page.",
        target_url="file:///tmp/basic.html",
        tags=["prompt"],
    )
    return WebAgentContextSnapshot(
        task=task,
        trace=TraceContext(
            run_id="run_prompt",
            run_dir="/tmp/run_prompt",
            trace_path="/tmp/run_prompt/trace.jsonl",
            transcript_path="/tmp/run_prompt/transcript.jsonl",
        ),
        version=VersionContext(),
        budget=task.budget,
        safety=task.safety,
        state=RuntimeState(status="context_built"),
    )

# From test_execution_prompt_integration.py
import json
from pathlib import Path

import pytest

from webscoper.runtime.execution.handler import WebAgentExecutionHandler
from webscoper.runtime.prompt.reminders import RuntimeReminderStore
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
