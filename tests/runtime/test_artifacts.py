from __future__ import annotations

# From test_evidence_store.py
import json
from pathlib import Path

from webscoper.runtime.artifacts.evidence import EvidenceStore


def test_evidence_store_add_list_and_context_pack() -> None:
    store = EvidenceStore()

    first = store.add_item(
        kind="page_observation",
        source_url="file:///tmp/basic.html",
        page_title="Basic",
        text="Hello",
    )
    second = store.add_item(
        kind="action_result",
        text="Clicked Quickstart.",
        metadata={"verified": True},
    )

    assert first.evidence_id == "ev_000001"
    assert second.evidence_id == "ev_000002"
    assert [item.evidence_id for item in store.list_items()] == [
        "ev_000001",
        "ev_000002",
    ]
    pack = store.to_context_pack(max_items=1)
    assert pack["evidence_count"] == 2
    assert len(pack["items"]) == 1
    assert pack["items"][0]["evidence_id"] == "ev_000001"


def test_evidence_store_writes_jsonl(tmp_path: Path) -> None:
    output_path = tmp_path / "evidence.jsonl"
    store = EvidenceStore(output_path)
    store.add_item(kind="text_excerpt", text="pip install playwright")

    store.write_jsonl()

    lines = output_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    payload = json.loads(lines[0])
    assert payload["evidence_id"] == "ev_000001"
    assert payload["kind"] == "text_excerpt"
    assert payload["text"] == "pip install playwright"

# From test_report_builder.py
from webscoper.runtime.artifacts.evidence import EvidenceStore
from webscoper.runtime.artifacts.report import FinalReportBuilder
from webscoper.schemas.task import TaskSpec


def test_final_report_builder_includes_evidence_ids() -> None:
    store = EvidenceStore()
    store.add_item(
        kind="page_observation",
        source_url="file:///tmp/basic.html",
        page_title="Basic",
        text="Quickstart",
    )
    task = TaskSpec(
        task_id="report_task",
        raw_input="Open local basic mock.",
        target_url="file:///tmp/basic.html",
    )

    report = FinalReportBuilder().build_markdown(task, store.list_items())

    assert "# VaniScope Task Report" in report
    assert "report_task" in report
    assert "ev_000001" in report
    assert "Page observation" in report

# From test_trace_recorder.py
import json
from pathlib import Path

from webscoper.runtime.artifacts.trace import TraceRecorder
from webscoper.schemas.trace import TraceStep


def test_trace_recorder_appends_jsonl(tmp_path: Path) -> None:
    recorder = TraceRecorder(run_dir=tmp_path / "run_test", run_id="run_test")
    step = TraceStep(
        step_id="step_001",
        run_id="run_test",
        phase="browser_runtime",
        actor="system",
        action_type="browser_open_observe",
        status="success",
    )

    recorder.record(step)

    assert recorder.trace_path.exists()
    lines = recorder.trace_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    payload = json.loads(lines[0])
    assert payload["action_type"] == "browser_open_observe"

# From test_transcript_store.py
import json
from pathlib import Path

from webscoper.runtime.artifacts.transcript import TranscriptStore


def test_transcript_store_appends_jsonl_event(tmp_path: Path) -> None:
    store = TranscriptStore(run_dir=tmp_path / "run", run_id="run_test")

    store.append("task_loaded", {"task_id": "test"})

    assert store.transcript_path.exists()
    lines = store.transcript_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1

    event = json.loads(lines[0])
    assert event["run_id"] == "run_test"
    assert event["event_type"] == "task_loaded"
    assert event["payload"]["task_id"] == "test"
    assert event["created_at"]

# From test_run_task_evidence_artifacts.py
import json
from pathlib import Path

import pytest

from webscoper.runtime.execution.handler import WebAgentExecutionHandler
from webscoper.schemas.action import ActionContract, ExpectedEffect
from webscoper.schemas.task import TaskSpec


@pytest.mark.asyncio
async def test_execution_handler_writes_evidence_and_report(
    tmp_path: Path,
) -> None:
    action = ActionContract(
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
    task = TaskSpec(
        task_id="evidence_artifacts",
        raw_input="Open local basic mock and click Quickstart.",
        target_url=Path("tests/fixtures/mock_site/basic.html").resolve().as_uri(),
        action=action,
        expected_effect=action.expected_effect,
    )
    handler = WebAgentExecutionHandler(output_root=tmp_path)

    observation = await handler.run(task)

    context = handler.last_context
    assert context is not None
    evidence_path = context.run_dir / "evidence.jsonl"
    report_path = context.run_dir / "final_report.md"
    review_path = context.run_dir / "review.json"
    review_summary_path = context.run_dir / "review_summary.md"
    assert "pip install playwright" in observation.visible_text_summary
    assert evidence_path.exists()
    assert report_path.exists()
    assert review_path.exists()
    assert review_summary_path.exists()

    evidence_items = [
        json.loads(line)
        for line in evidence_path.read_text(encoding="utf-8").splitlines()
    ]
    evidence_ids = [item["evidence_id"] for item in evidence_items]
    kinds = {item["kind"] for item in evidence_items}
    report = report_path.read_text(encoding="utf-8")
    review = json.loads(review_path.read_text(encoding="utf-8"))
    review_summary = review_summary_path.read_text(encoding="utf-8")
    transcript_events = _jsonl_values(
        context.transcript_store.transcript_path,
        "event_type",
    )

    assert evidence_ids[0] == "ev_000001"
    assert "page_observation" in kinds
    assert "action_result" in kinds
    assert "text_excerpt" in kinds
    assert "ev_000001" in report
    assert review["passed"] is True
    assert "VaniScope Review Summary" in review_summary
    assert "evidence_written" in transcript_events
    assert "final_report_built" in transcript_events
    assert "review_completed" in transcript_events


def _jsonl_values(path: Path, key: str) -> list[str]:
    return [
        json.loads(line)[key]
        for line in path.read_text(encoding="utf-8").splitlines()
    ]
