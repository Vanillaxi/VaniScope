from __future__ import annotations

from pathlib import Path

import pytest

from webscoper.eval.browser_eval import BrowserEvalRunner


@pytest.mark.asyncio
async def test_browser_eval_runner_passes_local_cases(tmp_path: Path) -> None:
    cases_path = Path("tests/fixtures/eval_cases/browser_runtime_cases.json")

    summary = await BrowserEvalRunner(
        cases_path=cases_path,
        output_root=tmp_path,
    ).run()

    run_dir = tmp_path / summary.run_id
    tags = {tag for result in summary.results for tag in result.metrics.get("tags", [])}

    assert summary.total_cases >= 5
    assert summary.passed_cases == summary.total_cases
    assert (run_dir / "score.json").exists()
    assert (run_dir / "report.md").exists()
    assert "lazy" in tags
    assert "risk" in tags
