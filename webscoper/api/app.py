from __future__ import annotations

from fastapi import FastAPI, HTTPException

from webscoper.api.schemas import (
    TaskArtifactContentResponse,
    TaskArtifactListResponse,
    TaskCreateRequest,
    TaskCreateResponse,
    TaskStatusResponse,
)
from webscoper.api.task_service import TaskService


app = FastAPI(title="VaniScope API", version="0.1.0")
task_service = TaskService()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "vaniscope-api"}


@app.post("/tasks", response_model=TaskCreateResponse)
def create_task(request: TaskCreateRequest) -> TaskCreateResponse:
    return task_service.create_and_run_task(request)


@app.get("/tasks/{task_id}", response_model=TaskStatusResponse)
def get_task(task_id: str) -> TaskStatusResponse:
    return task_service.get_task_status(task_id)


@app.get("/tasks/{task_id}/artifacts", response_model=TaskArtifactListResponse)
def list_artifacts(task_id: str) -> TaskArtifactListResponse:
    try:
        return task_service.list_artifacts(task_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


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
