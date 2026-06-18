from __future__ import annotations

import json
from pathlib import Path

from webscoper.runtime.task_runner import run_browser_task_sync


def test_run_task_fake_llm_revise_loop_generates_artifacts(tmp_path: Path) -> None:
    result = run_browser_task_sync(
        url="tests/fixtures/mock_site/basic.html",
        click="Quickstart",
        expect="pip install playwright",
        planner="deterministic",
        reviewer="fake_llm",
        revise_attempts=1,
        workspace=Path("tests/fixtures/workspace"),
        reminders=["Review and revise the report against evidence."],
        output_root=tmp_path,
    )
    context = result.handler.last_context
    assert context is not None
    run_dir = context.run_dir

    assert (run_dir / "revision_plan.json").exists()
    assert (run_dir / "revised_report.md").exists()
    assert (run_dir / "final_review.json").exists()
    assert (run_dir / "revise_loop.json").exists()
    final_review = json.loads((run_dir / "final_review.json").read_text())
    assert final_review["passed"] is True
    assert "ev_000001" in (run_dir / "revised_report.md").read_text()
