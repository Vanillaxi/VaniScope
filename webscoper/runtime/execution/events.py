from __future__ import annotations

import asyncio
import json
import threading
from collections import defaultdict
from collections.abc import AsyncIterator, Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from webscoper.schemas.runtime import TaskEvent, TaskEventKind


TERMINAL_EVENT_KINDS = {
    "task_finished",
    "task_succeeded",
    "task_failed",
    "task_blocked",
    "task_rejected",
    "task_canceled",
    "partial_report_generated",
    "resume_failed",
}


class TaskEventSink(Protocol):
    def __call__(
        self,
        kind: TaskEventKind,
        message: str,
        payload: dict[str, Any] | None = None,
    ) -> None:
        ...


class TaskEventStore:
    def __init__(self) -> None:
        self._events: dict[str, list[TaskEvent]] = defaultdict(list)
        self._next_ids: dict[str, int] = defaultdict(lambda: 1)
        self._lock = threading.Lock()

    def append(self, event: TaskEvent) -> TaskEvent:
        payload = _json_safe(event.payload)
        with self._lock:
            next_id = self._next_ids[event.task_id]
            event_id = event.event_id or f"evt_{next_id:06d}"
            created_at = event.created_at or datetime.now(UTC).isoformat()
            stored = event.model_copy(
                update={
                    "event_id": event_id,
                    "created_at": created_at,
                    "payload": payload,
                }
            )
            self._next_ids[event.task_id] = next_id + 1
            self._events[event.task_id].append(stored)
            return stored

    def list_events(self, task_id: str) -> list[TaskEvent]:
        with self._lock:
            return list(self._events.get(task_id, []))

    def write_jsonl(self, task_id: str, output_path: Path) -> None:
        events = self.list_events(task_id)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("w", encoding="utf-8") as file:
            for event in events:
                file.write(json.dumps(event.model_dump(mode="json"), ensure_ascii=False))
                file.write("\n")


class TaskEventSubscription:
    def __init__(
        self,
        task_id: str,
        queue: asyncio.Queue[TaskEvent],
        unsubscribe: Callable[[str, asyncio.Queue[TaskEvent]], None],
    ) -> None:
        self.task_id = task_id
        self._queue = queue
        self._unsubscribe = unsubscribe
        self._closed = False

    async def __aiter__(self) -> AsyncIterator[TaskEvent]:
        try:
            while True:
                event = await self._queue.get()
                yield event
                if event.kind in TERMINAL_EVENT_KINDS:
                    break
        finally:
            self.close()

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._unsubscribe(self.task_id, self._queue)


class InMemoryTaskEventBus:
    def __init__(self) -> None:
        self._subscribers: dict[str, set[asyncio.Queue[TaskEvent]]] = defaultdict(set)

    def publish(self, event: TaskEvent) -> None:
        for queue in list(self._subscribers.get(event.task_id, set())):
            queue.put_nowait(event)

    def open_subscription(self, task_id: str) -> TaskEventSubscription:
        queue: asyncio.Queue[TaskEvent] = asyncio.Queue()
        self._subscribers[task_id].add(queue)
        return TaskEventSubscription(task_id, queue, self._unsubscribe)

    async def subscribe(self, task_id: str) -> AsyncIterator[TaskEvent]:
        subscription = self.open_subscription(task_id)
        async for event in subscription:
            yield event

    def _unsubscribe(
        self,
        task_id: str,
        queue: asyncio.Queue[TaskEvent],
    ) -> None:
        subscribers = self._subscribers.get(task_id)
        if subscribers is None:
            return
        subscribers.discard(queue)
        if not subscribers:
            self._subscribers.pop(task_id, None)


def _json_safe(payload: dict[str, Any]) -> dict[str, Any]:
    return json.loads(json.dumps(payload, ensure_ascii=False, default=str))
