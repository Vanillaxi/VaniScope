from __future__ import annotations

from webscoper.runtime.prompt_builder import DynamicPromptBuilder
from webscoper.schemas.compaction import (
    CompactedBrowserState,
    CompactedEvidenceRef,
    CompactedRecoveryState,
    CompactedRiskState,
    CompactedStep,
    ContextPack,
)
from webscoper.schemas.context import RuntimeState, TraceContext, WebAgentContextSnapshot
from webscoper.schemas.task import TaskSpec
from webscoper.schemas.version import VersionContext
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
