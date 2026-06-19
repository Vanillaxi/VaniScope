from __future__ import annotations

import pytest

from webscoper.runtime.inspector.loader import RunArtifactLoader


def test_run_artifact_loader_returns_empty_for_missing_artifacts(tmp_path) -> None:
    runs_dir = tmp_path / "runs"
    run_dir = runs_dir / "task_loader"
    run_dir.mkdir(parents=True)
    (run_dir / "prompt_preview.md").write_text("x" * 20, encoding="utf-8")

    loader = RunArtifactLoader(runs_dir, "task_loader", max_text_chars=8)

    assert loader.read_jsonl("events.jsonl") == []
    assert loader.read_json("review.json") == {}
    assert loader.read_text("missing.md") == ""
    assert loader.read_text("prompt_preview.md").startswith("xxxxxxxx")
    assert "truncated" in loader.read_text("prompt_preview.md")


def test_run_artifact_loader_rejects_path_traversal(tmp_path) -> None:
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir()

    with pytest.raises(ValueError):
        RunArtifactLoader(runs_dir, "..")

    loader = RunArtifactLoader(runs_dir, "task_safe")
    with pytest.raises(ValueError):
        loader.read_text("../secret.txt")
