from __future__ import annotations

import json
from pathlib import Path

from webscoper.runtime.task_runner import run_browser_task_sync


def test_risk_block_writes_artifacts_without_clicking(tmp_path: Path) -> None:
    output = run_browser_task_sync(
        url="tests/fixtures/mock_site/risk_actions.html",
        click="Delete account",
        expect="Delete account",
        planner="deterministic",
        workspace="tests/fixtures/workspace",
        reminders=["Do not perform dangerous actions without approval."],
        output_root=tmp_path / "runs",
    )

    context = output.handler.last_context
    assert context is not None
    assert context.state.status == "blocked"

    risk_report_path = context.run_dir / "risk_report.json"
    approvals_path = context.run_dir / "approvals.jsonl"
    transcript_path = context.transcript_store.transcript_path

    assert risk_report_path.is_file()
    assert approvals_path.is_file()
    report = json.loads(risk_report_path.read_text(encoding="utf-8"))
    assert report["blocked"] == 1
    assert report["approval_required"] == 0
    assert report["total_risk_signals"] >= 1
    assert "risk_blocked" in transcript_path.read_text(encoding="utf-8")
