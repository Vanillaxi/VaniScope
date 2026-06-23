from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal


TaskControlAction = Literal["pause", "resume", "cancel", "stop_and_summarize"]


@dataclass
class TaskControlState:
    task_id: str
    pause_requested: bool = False
    cancel_requested: bool = False
    stop_requested: bool = False
    budget_override: bool = False
    continue_for_task: bool = False
    aggressive_compaction_requested: bool = False
    updated_at: str = field(default_factory=lambda: _utc_now())

    def snapshot(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "pause_requested": self.pause_requested,
            "cancel_requested": self.cancel_requested,
            "stop_requested": self.stop_requested,
            "budget_override": self.budget_override,
            "continue_for_task": self.continue_for_task,
            "aggressive_compaction_requested": self.aggressive_compaction_requested,
            "updated_at": self.updated_at,
        }


class TaskControlStore:
    def __init__(self) -> None:
        self._states: dict[str, TaskControlState] = {}
        self._lock = threading.Lock()

    def get(self, task_id: str) -> TaskControlState:
        with self._lock:
            state = self._states.get(task_id)
            if state is None:
                state = TaskControlState(task_id=task_id)
                self._states[task_id] = state
            return state

    def request(self, task_id: str, action: TaskControlAction) -> TaskControlState:
        with self._lock:
            state = self._states.get(task_id)
            if state is None:
                state = TaskControlState(task_id=task_id)
                self._states[task_id] = state
            if action == "pause":
                state.pause_requested = True
            elif action == "resume":
                state.pause_requested = False
                state.cancel_requested = False
                state.stop_requested = False
            elif action == "cancel":
                state.cancel_requested = True
                state.pause_requested = False
                state.stop_requested = False
            elif action == "stop_and_summarize":
                state.stop_requested = True
                state.pause_requested = False
            state.updated_at = _utc_now()
            return state

    def resolve_budget_approval(
        self,
        task_id: str,
        *,
        continue_once: bool = False,
        continue_for_task: bool = False,
        continue_with_compaction: bool = False,
    ) -> TaskControlState:
        with self._lock:
            state = self._states.get(task_id)
            if state is None:
                state = TaskControlState(task_id=task_id)
                self._states[task_id] = state
            if continue_once:
                state.budget_override = True
            if continue_for_task:
                state.continue_for_task = True
            if continue_with_compaction:
                state.aggressive_compaction_requested = True
                state.budget_override = True
            state.updated_at = _utc_now()
            return state

    def clear_transient_flags(self, task_id: str) -> None:
        with self._lock:
            state = self._states.get(task_id)
            if state is None:
                return
            state.pause_requested = False
            state.stop_requested = False
            state.budget_override = False
            state.aggressive_compaction_requested = False
            state.updated_at = _utc_now()

    def write_jsonl(self, task_id: str, output_path: Path) -> None:
        state = self.get(task_id)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(state.snapshot(), ensure_ascii=False) + "\n")


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()
