from __future__ import annotations

import json
from typing import Any

from webscoper.runtime.execution.events import TaskEventSink
from webscoper.runtime.artifacts.evidence import EvidenceStore
from webscoper.runtime.artifacts.trace import TraceRecorder
from webscoper.runtime.artifacts.transcript import TranscriptStore
from webscoper.schemas.browser import RecoveryAttempt, RecoveryResult
from webscoper.schemas.artifact import TraceStep


class RecoveryTelemetry:
    def __init__(
        self,
        *,
        trace_recorder: TraceRecorder | None = None,
        event_sink: TaskEventSink | None = None,
        evidence_store: EvidenceStore | None = None,
        transcript_store: TranscriptStore | None = None,
        task_id: str | None = None,
    ) -> None:
        self.trace_recorder = trace_recorder
        self.event_sink = event_sink
        self.evidence_store = evidence_store
        self.transcript_store = transcript_store
        self.task_id = task_id

    def emit_started(
        self,
        *,
        error_type: str,
        target_hint: str,
        strategies: list[str],
    ) -> None:
        emit_recovery_event(
            self.event_sink,
            self.transcript_store,
            "recovery_started",
            "Recovery started",
            self.task_id,
            {
                "error_type": error_type,
                "target_hint": target_hint,
                "strategies": strategies,
            },
        )

    def emit_attempt_started(self, attempt: RecoveryAttempt) -> None:
        record_recovery_trace(
            self.trace_recorder,
            attempt,
            "recovery_attempt",
            "running",
        )
        emit_recovery_event(
            self.event_sink,
            self.transcript_store,
            "recovery_attempt_started",
            "Recovery attempt started",
            self.task_id,
            attempt.model_dump(mode="json"),
        )

    def emit_attempt_finished(self, attempt: RecoveryAttempt) -> None:
        write_recovery_attempt(self.trace_recorder, attempt)
        record_recovery_trace(
            self.trace_recorder,
            attempt,
            "recovery_attempt",
            attempt.status,
        )
        emit_recovery_event(
            self.event_sink,
            self.transcript_store,
            "recovery_attempt_finished",
            "Recovery attempt finished",
            self.task_id,
            attempt.model_dump(mode="json"),
        )

    def emit_result(self, result: RecoveryResult) -> None:
        emit_recovery_result(
            self.event_sink,
            self.transcript_store,
            self.task_id,
            result,
        )

    def add_recovery_evidence(
        self,
        result: RecoveryResult,
        attempt: RecoveryAttempt,
    ) -> None:
        add_recovery_evidence(self.evidence_store, result, attempt)


def write_recovery_attempt(
    trace_recorder: TraceRecorder | None,
    attempt: RecoveryAttempt,
) -> None:
    if trace_recorder is None:
        return
    path = trace_recorder.run_dir / "recovery.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(attempt.model_dump(mode="json"), ensure_ascii=False))
        file.write("\n")


def record_recovery_trace(
    trace_recorder: TraceRecorder | None,
    attempt: RecoveryAttempt,
    action_type: str,
    status: str,
) -> None:
    if trace_recorder is None:
        return
    trace_recorder.record(
        TraceStep(
            step_id=attempt.attempt_id,
            run_id=trace_recorder.run_id,
            phase="browser_recovery",
            actor="system",
            action_type=action_type,
            status=status,
            url_before=attempt.before_url,
            url_after=attempt.after_url,
            observation=attempt.model_dump(mode="json"),
            error_type=attempt.error_type.value,
            error_message=attempt.reason if status not in {"succeeded", "running"} else None,
        )
    )


def emit_recovery_event(
    event_sink: TaskEventSink | None,
    transcript_store: TranscriptStore | None,
    event_type: str,
    message: str,
    task_id: str | None,
    payload: dict[str, Any],
) -> None:
    safe_payload = json.loads(json.dumps(payload, ensure_ascii=False, default=str))
    if transcript_store is not None:
        try:
            transcript_store.append(event_type, safe_payload)
        except Exception:
            pass
    if event_sink is not None and task_id is not None:
        try:
            event_sink(event_type, message, safe_payload)
        except Exception:
            pass


def emit_recovery_result(
    event_sink: TaskEventSink | None,
    transcript_store: TranscriptStore | None,
    task_id: str | None,
    result: RecoveryResult,
) -> None:
    if result.blocked:
        event_type = "recovery_blocked"
        message = "Recovery blocked"
    elif result.recovered:
        event_type = "recovery_succeeded"
        message = "Recovery succeeded"
    else:
        event_type = "recovery_failed"
        message = "Recovery failed"
    emit_recovery_event(
        event_sink,
        transcript_store,
        event_type,
        message,
        task_id,
        {
            "recovered": result.recovered,
            "blocked": result.blocked,
            "attempts": len(result.attempts),
            "final_error_type": result.final_error_type.value
            if result.final_error_type is not None
            else None,
            "message": result.message,
        },
    )
    emit_recovery_event(
        event_sink,
        transcript_store,
        "recovery_finished",
        "Recovery finished",
        task_id,
        {
            "status": event_type.replace("recovery_", ""),
            "recovered": result.recovered,
            "blocked": result.blocked,
            "attempts": len(result.attempts),
            "final_error_type": result.final_error_type.value
            if result.final_error_type is not None
            else None,
            "message": result.message,
        },
    )


def add_recovery_evidence(
    evidence_store: EvidenceStore | None,
    result: RecoveryResult,
    attempt: RecoveryAttempt,
) -> None:
    if evidence_store is None:
        return
    try:
        evidence_store.add_item(
            kind="action_result",
            source_url=attempt.after_url,
            text=result.message,
            metadata={
                "recovery_result": result.model_dump(mode="json"),
                "recovery_attempt": attempt.model_dump(mode="json"),
            },
        )
        evidence_store.write_jsonl()
    except Exception:
        return
