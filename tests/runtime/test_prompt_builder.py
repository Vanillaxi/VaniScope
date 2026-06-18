from __future__ import annotations

from webscoper.runtime.prompt_builder import DynamicPromptBuilder
from webscoper.schemas.context import (
    RuntimeState,
    TraceContext,
    WebAgentContextSnapshot,
)
from webscoper.schemas.prompt import AgentsMdInstruction, RuntimeReminder
from webscoper.schemas.task import TaskSpec
from webscoper.schemas.version import VersionContext
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
