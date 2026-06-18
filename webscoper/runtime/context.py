from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from webscoper.runtime.artifacts.evidence import EvidenceStore
from webscoper.runtime.artifacts.trace import TraceRecorder
from webscoper.runtime.artifacts.transcript import TranscriptStore
from webscoper.schemas.context import (
    RuntimeState,
    TraceContext,
    WebAgentContextSnapshot,
)
from webscoper.schemas.task import TaskSpec
from webscoper.schemas.version import VersionContext


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
        )
