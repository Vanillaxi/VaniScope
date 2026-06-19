from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_run_task_script_uses_langgraph_workflow(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            "scripts/run_task.py",
            "--url",
            "tests/fixtures/mock_site/basic.html",
            "--click",
            "Quickstart",
            "--expect",
            "pip install playwright",
            "--planner",
            "deterministic",
            "--workspace",
            "tests/fixtures/workspace",
            "--reminder",
            "This is a test runtime reminder.",
            "--output-root",
            str(tmp_path),
        ],
        check=True,
        text=True,
        capture_output=True,
    )

    assert "workflow_backend: langgraph" in result.stdout
    assert "workflow_state_path:" in result.stdout


def test_run_task_script_rejects_legacy_workflow_argument(tmp_path: Path) -> None:
    legacy_workflow = "nat" + "ive"
    result = subprocess.run(
        [
            sys.executable,
            "scripts/run_task.py",
            "--url",
            "tests/fixtures/mock_site/basic.html",
            "--workflow",
            legacy_workflow,
            "--output-root",
            str(tmp_path),
        ],
        check=False,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 2
    assert f"unrecognized arguments: --workflow {legacy_workflow}" in result.stderr
