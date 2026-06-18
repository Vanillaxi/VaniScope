from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_run_reviewer_eval_script_writes_outputs(tmp_path: Path) -> None:
    output_dir = tmp_path / "reviewer_eval_local"

    result = subprocess.run(
        [
            sys.executable,
            "scripts/run_reviewer_eval.py",
            "--cases",
            "tests/fixtures/reviewer_eval_cases.json",
            "--output-dir",
            str(output_dir),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert (output_dir / "score.json").exists()
    assert (output_dir / "report.md").exists()
    score = json.loads((output_dir / "score.json").read_text(encoding="utf-8"))
    assert score["total"] >= 8
    assert score["passed"] == score["total"]
    assert score["pass_rate"] == 1.0
    report = (output_dir / "report.md").read_text(encoding="utf-8")
    assert "# VaniScope Reviewer Eval Report" in report
    assert "valid_report_with_evidence" in report
