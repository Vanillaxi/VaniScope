from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from webscoper.schemas.trace import TraceStep


class TraceRecorder:
    def __init__(self, run_dir: Path, run_id: str) -> None:
        self.run_dir = run_dir
        self.run_id = run_id
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.trace_path = self.run_dir / "trace.jsonl"

    def record(self, step: TraceStep) -> None:
        payload = self._dump_step(step)
        with self.trace_path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(payload, ensure_ascii=False))
            file.write("\n")

    @staticmethod
    def _dump_step(step: TraceStep) -> dict[str, Any]:
        if hasattr(step, "model_dump"):
            return step.model_dump(mode="json")
        return step.dict()
