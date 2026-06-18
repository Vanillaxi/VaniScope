from __future__ import annotations

import json
from pathlib import Path

import pytest

from webscoper.runtime.execution import WebAgentExecutionHandler
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
