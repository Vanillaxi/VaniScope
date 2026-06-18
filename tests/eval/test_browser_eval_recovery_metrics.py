from __future__ import annotations

import json
from pathlib import Path

import pytest

from webscoper.eval.browser_eval import BrowserEvalRunner


@pytest.mark.asyncio
async def test_browser_eval_score_includes_recovery_metrics(tmp_path: Path) -> None:
    summary = await BrowserEvalRunner(
        cases_path=Path("tests/fixtures/eval_cases/browser_runtime_cases.json"),
        output_root=tmp_path,
    ).run()

    score = json.loads((tmp_path / summary.run_id / "score.json").read_text())

    assert score["recovery_attempt_count"] >= 3
    assert score["recovered_case_count"] >= 3
    assert score["recovery_success_rate"] > 0
    assert "blocked_recovery_count" in score
