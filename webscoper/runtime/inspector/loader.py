from __future__ import annotations

import json
from pathlib import Path
from typing import Any


DEFAULT_MAX_TEXT_CHARS = 200_000


class RunArtifactLoader:
    def __init__(
        self,
        runs_dir: Path,
        task_id: str,
        *,
        max_text_chars: int = DEFAULT_MAX_TEXT_CHARS,
    ) -> None:
        self.runs_dir = runs_dir.resolve()
        self.task_id = task_id
        self.max_text_chars = max_text_chars
        self.run_dir = self._resolve_run_dir(task_id)

    def exists(self) -> bool:
        return self.run_dir.is_dir()

    def list_artifacts(self) -> list[str]:
        if not self.exists():
            return []
        return sorted(path.name for path in self.run_dir.iterdir() if path.is_file())

    def read_json(self, artifact_name: str) -> dict[str, Any]:
        path = self._artifact_path(artifact_name)
        if path is None:
            return {}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return payload if isinstance(payload, dict) else {}

    def read_jsonl(self, artifact_name: str) -> list[dict[str, Any]]:
        path = self._artifact_path(artifact_name)
        if path is None:
            return []
        rows: list[dict[str, Any]] = []
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return []
        for line_no, line in enumerate(lines, start=1):
            if not line.strip():
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                payload.setdefault("_line", line_no)
                rows.append(payload)
        return rows

    def read_text(self, artifact_name: str) -> str:
        path = self._artifact_path(artifact_name)
        if path is None:
            return ""
        try:
            value = path.read_text(encoding="utf-8")
        except OSError:
            return ""
        if len(value) <= self.max_text_chars:
            return value
        return (
            value[: self.max_text_chars]
            + f"\n\n[truncated: original length {len(value)} characters]"
        )

    def _resolve_run_dir(self, task_id: str) -> Path:
        if not task_id or "/" in task_id or "\\" in task_id or task_id in {".", ".."}:
            raise ValueError("Task id is invalid.")
        run_dir = (self.runs_dir / task_id).resolve()
        if run_dir.parent != self.runs_dir:
            raise ValueError("Task run directory escapes runs root.")
        return run_dir

    def _artifact_path(self, artifact_name: str) -> Path | None:
        if not artifact_name or "/" in artifact_name or "\\" in artifact_name:
            raise ValueError("Artifact name is invalid.")
        path = (self.run_dir / artifact_name).resolve()
        if path.parent != self.run_dir:
            raise ValueError("Artifact path escapes task run directory.")
        if not path.is_file():
            return None
        return path


ArtifactLoader = RunArtifactLoader
