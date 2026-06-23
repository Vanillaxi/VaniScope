from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from webscoper.runtime.artifacts.evidence import EvidenceStore
from webscoper.runtime.artifacts.trace import TraceRecorder, TranscriptStore
from webscoper.schemas.browser import PageObservation
from webscoper.schemas.runtime import (
    LoadedToolContext,
    RuntimeState,
    SkillPromptContext,
    SkillSession,
    TraceContext,
    VersionContext,
    WebAgentContextSnapshot,
)
from webscoper.schemas.task import TaskSpec


@dataclass
class WebAgentContext:
    task: TaskSpec
    run_id: str
    run_dir: Path
    trace_recorder: TraceRecorder
    transcript_store: TranscriptStore
    version: VersionContext
    state: RuntimeState
    evidence_store: EvidenceStore | None = None
    skill_context: SkillPromptContext | None = None
    skill_session: SkillSession | None = None
    loaded_tools: list[LoadedToolContext] | None = None

    def snapshot(self) -> WebAgentContextSnapshot:
        return WebAgentContextSnapshot(
            task=self.task,
            trace=TraceContext(
                run_id=self.run_id,
                run_dir=str(self.run_dir),
                trace_path=str(self.trace_recorder.trace_path),
                transcript_path=str(self.transcript_store.transcript_path),
            ),
            version=self.version,
            budget=self.task.budget,
            safety=self.task.safety,
            state=self.state,
            loaded_tools=self.loaded_tools or [],
            skill_session=self.skill_session,
        )

    @property
    def loaded_tool_ids(self) -> list[str]:
        return [tool.tool_id for tool in self.loaded_tools or []]

    def record_loaded_tool(
        self,
        descriptor: dict[str, Any],
        *,
        source: str,
        usage_rules: list[str] | None = None,
    ) -> LoadedToolContext:
        tools = list(self.loaded_tools or [])
        tool_id = str(descriptor.get("tool_id") or descriptor.get("id") or "")
        existing = next((tool for tool in tools if tool.tool_id == tool_id), None)
        if existing is not None:
            return existing
        loaded = LoadedToolContext(
            tool_id=tool_id,
            loaded_at=datetime.now(UTC).isoformat(),
            descriptor_digest=_digest_descriptor(descriptor),
            full_schema=descriptor,
            usage_rules=usage_rules or [],
            source=source,
        )
        tools.append(loaded)
        self.loaded_tools = tools
        if self.skill_session is not None and tool_id not in self.skill_session.loaded_tool_ids:
            active_tools = list(self.skill_session.active_tools)
            if tool_id not in active_tools:
                active_tools.append(tool_id)
            self.skill_session = self.skill_session.model_copy(
                update={
                    "loaded_tool_ids": [*self.skill_session.loaded_tool_ids, tool_id],
                    "active_tools": active_tools,
                }
            )
        return loaded


def task_payload(task: TaskSpec) -> dict:
    return {
        "task_id": task.task_id,
        "task_type": task.task_type,
        "target_url": task.target_url,
        "has_action": task.action is not None,
        "tags": task.tags,
        "budget": task.budget.model_dump(mode="json"),
        "safety": task.safety.model_dump(mode="json"),
    }


def state_payload(context: WebAgentContext) -> dict:
    return {
        "task_id": context.task.task_id,
        "run_id": context.run_id,
        "run_dir": str(context.run_dir),
        "state": context.state.model_dump(mode="json"),
    }


def status_from_loop_error(error_type: str | None) -> str | None:
    if error_type == "RISK_APPROVAL_REQUIRED":
        return "requires_approval"
    if error_type in {
        "RISK_BLOCKED",
        "PUBLIC_WEB_BLOCKED",
        "UNKNOWN_TOOL",
        "TOOL_DISABLED",
        "TOOL_DANGEROUS",
        "TOOL_HIDDEN",
        "TOOL_COMPATIBILITY_WRAPPER_REJECTED",
    }:
        return "blocked"
    return None


def observation_summary(observation: PageObservation) -> dict:
    return {
        "url": observation.url,
        "title": observation.title,
        "risk_signals_count": len(observation.risk_signals),
        "interactive_elements_count": len(observation.interactive_elements),
        "screenshot_path": observation.screenshot_path,
    }


def _digest_descriptor(descriptor: dict[str, Any]) -> str:
    payload = json.dumps(descriptor, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]
