from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_run_workflow_eval_script_writes_outputs(tmp_path: Path) -> None:
    cases_path = tmp_path / "workflow_cases.json"
    fixture_cases = json.loads(
        Path("tests/fixtures/workflow_eval_cases.json").read_text(encoding="utf-8")
    )
    cases_path.write_text(
        json.dumps([fixture_cases[0]], indent=2),
        encoding="utf-8",
    )
    output_dir = tmp_path / "workflow_eval"

    result = subprocess.run(
        [
            sys.executable,
            "scripts/run_workflow_eval.py",
            "--cases",
            str(cases_path),
            "--output-dir",
            str(output_dir),
        ],
        check=True,
        text=True,
        capture_output=True,
    )

    assert "total: 1" in result.stdout
    assert "failed: 0" in result.stdout
    assert (output_dir / "score.json").exists()
    assert (output_dir / "report.md").exists()
