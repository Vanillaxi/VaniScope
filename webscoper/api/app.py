from __future__ import annotations

import json

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse

from webscoper.api.schemas import (
    TaskArtifactContentResponse,
    TaskArtifactListResponse,
    TaskCreateRequest,
    TaskCreateResponse,
    TaskStatusResponse,
)
from webscoper.api.task_service import TaskService
from webscoper.runtime.events import TERMINAL_EVENT_KINDS
from webscoper.schemas.events import TaskEvent


app = FastAPI(title="VaniScope API", version="0.1.0")
task_service = TaskService()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "vaniscope-api"}


@app.post("/tasks", response_model=TaskCreateResponse)
def create_task(request: TaskCreateRequest) -> TaskCreateResponse:
    return task_service.create_and_run_task(request)


@app.post("/tasks/async", response_model=TaskCreateResponse)
async def create_task_async(request: TaskCreateRequest) -> TaskCreateResponse:
    return await task_service.create_and_run_task_async(request)


@app.get("/tasks/{task_id}", response_model=TaskStatusResponse)
def get_task(task_id: str) -> TaskStatusResponse:
    return task_service.get_task_status(task_id)


@app.get("/tasks/{task_id}/events")
async def stream_task_events(task_id: str) -> StreamingResponse:
    if _task_missing(task_id):
        raise HTTPException(status_code=404, detail=f"Task not found: {task_id}")

    async def event_generator():
        subscription = task_service.open_event_subscription(task_id)
        seen_event_ids: set[str] = set()
        try:
            history = task_service.get_events(task_id)
            if not history and task_service.get_task_status(task_id).status != "running":
                return

            for event in history:
                seen_event_ids.add(event.event_id)
                yield format_sse(event)
                if event.kind in TERMINAL_EVENT_KINDS:
                    return

            async for event in subscription:
                if event.event_id in seen_event_ids:
                    continue
                seen_event_ids.add(event.event_id)
                yield format_sse(event)
                if event.kind in TERMINAL_EVENT_KINDS:
                    return
        finally:
            subscription.close()

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
    )


@app.get("/tasks/{task_id}/artifacts", response_model=TaskArtifactListResponse)
def list_artifacts(task_id: str) -> TaskArtifactListResponse:
    try:
        return task_service.list_artifacts(task_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def format_sse(event: TaskEvent) -> str:
    data = json.dumps(event.model_dump(mode="json"), ensure_ascii=False)
    return f"event: {event.kind}\ndata: {data}\n\n"


def _task_missing(task_id: str) -> bool:
    if task_service.get_events(task_id):
        return False
    return task_service.get_task_status(task_id).status == "not_found"


@app.get(
    "/tasks/{task_id}/artifacts/{artifact_name}",
    response_model=TaskArtifactContentResponse,
)
def read_artifact(
    task_id: str,
    artifact_name: str,
) -> TaskArtifactContentResponse:
    try:
        return task_service.read_artifact(task_id, artifact_name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
