from __future__ import annotations

import json
import os

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from webscoper.api.schemas import (
    ApprovalDecisionRequest,
    ApprovalDecisionResponse,
    ConversationCreateRequest,
    ConversationDetailResponse,
    ConversationResponse,
    DiagnosticsResponse,
    MessageResponse,
    RuntimeInspectorResponse,
    RuntimeTimelineResponse,
    TaskArtifactContentResponse,
    TaskArtifactListResponse,
    TaskCreateRequest,
    TaskCreateResponse,
    TaskStatusResponse,
)
from webscoper.api.diagnostics import build_diagnostics
from webscoper.api.task_service import TaskService
from webscoper.runtime.execution.events import TERMINAL_EVENT_KINDS
from webscoper.schemas.runtime import TaskEvent
from webscoper.schemas.runtime import ApprovalRequest

# FastAPI

app = FastAPI(title="VaniScope API", version="0.1.0")
task_service = TaskService()

_cors_origins = [
    origin.strip()
    for origin in os.getenv("VANISCOPE_CORS_ORIGINS", "http://localhost:3000").split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 健康检查
@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "vaniscope-api"}


@app.get("/diagnostics", response_model=DiagnosticsResponse)
def diagnostics() -> DiagnosticsResponse:
    return build_diagnostics(task_service.runs_dir, task_service.web_config)


@app.post("/conversations", response_model=ConversationResponse)
def create_conversation(request: ConversationCreateRequest) -> ConversationResponse:
    return task_service.create_conversation(
        title=request.title,
        metadata=request.metadata_json,
    )


@app.get("/conversations", response_model=list[ConversationResponse])
def list_conversations() -> list[ConversationResponse]:
    return task_service.list_conversations()


@app.get("/conversations/{conversation_id}", response_model=ConversationDetailResponse)
def get_conversation(conversation_id: str) -> ConversationDetailResponse:
    try:
        return task_service.get_conversation(conversation_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/conversations/{conversation_id}/messages", response_model=list[MessageResponse])
def list_conversation_messages(conversation_id: str) -> list[MessageResponse]:
    try:
        return task_service.list_messages(conversation_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

# 创建并同步运行任务
@app.post("/tasks", response_model=TaskCreateResponse)
def create_task(request: TaskCreateRequest) -> TaskCreateResponse:
    return task_service.create_and_run_task(request)

# 创建并异步运行任务
@app.post("/tasks/async", response_model=TaskCreateResponse)
async def create_task_async(request: TaskCreateRequest) -> TaskCreateResponse:
    return await task_service.create_and_run_task_async(request)

# 查看任务状态
@app.get("/tasks/{task_id}", response_model=TaskStatusResponse)
def get_task(task_id: str) -> TaskStatusResponse:
    return task_service.get_task_status(task_id)


@app.get("/tasks/{task_id}/timeline", response_model=RuntimeTimelineResponse)
def get_task_timeline(task_id: str) -> RuntimeTimelineResponse:
    try:
        return task_service.get_timeline(task_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/tasks/{task_id}/inspector", response_model=RuntimeInspectorResponse)
def get_task_inspector(task_id: str) -> RuntimeInspectorResponse:
    try:
        return task_service.get_inspector(task_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

# SSE流式事件
@app.get("/tasks/{task_id}/events")
async def stream_task_events(task_id: str) -> StreamingResponse:
    # 先检查任务是否存在
    if _task_missing(task_id):
        raise HTTPException(status_code=404, detail=f"Task not found: {task_id}")

    # 异步生成器
    async def event_generator():
        # 给这个任务开一个事件订阅，只要任务产生新事件，就可以从这个subscription里面拿到
        subscription = task_service.open_event_subscription(task_id)
        # 用set集合去重，因为一开始会发送历史事件，后面又会监听新事件
        seen_event_ids: set[str] = set()

        # 确保关闭订阅，资源清理
        try:
            history = task_service.get_events(task_id)
            # 不是历史事件而且任务不在running ，那就是没东西推送
            if not history and task_service.get_task_status(task_id).status != "running":
                return

            # 把历史事件逐个发送给前端
            for event in history:
                seen_event_ids.add(event.event_id)
                yield format_sse(event)

            # 任务已经结束，不再监听
            if task_service.get_task_status(task_id).status != "running":
                return

            # 继续监听实时新事件
            async for event in subscription:
                if event.event_id in seen_event_ids:
                    continue
                seen_event_ids.add(event.event_id)
                yield format_sse(event)
                if event.kind in TERMINAL_EVENT_KINDS:
                    return
        finally:
            subscription.close()

    # 把刚才的生成器包装成HTTP流式响应，而不是普通JSON
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )

# 查看任务产物列表
@app.get("/tasks/{task_id}/artifacts", response_model=TaskArtifactListResponse)
def list_artifacts(task_id: str) -> TaskArtifactListResponse:
    try:
        return task_service.list_artifacts(task_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

#查看某个任务的审批请求
@app.get("/tasks/{task_id}/approvals", response_model=list[ApprovalRequest])
def list_task_approvals(task_id: str) -> list[ApprovalRequest]:
    try:
        return task_service.list_approvals(task_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

# 查询审批
@app.get("/approvals/{approval_id}", response_model=ApprovalRequest)
def get_approval(approval_id: str) -> ApprovalRequest:
    try:
        return task_service.get_approval(approval_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

# 提交审批决定
@app.post("/approvals/{approval_id}/decision", response_model=ApprovalDecisionResponse)
def decide_approval(
    approval_id: str,
    request: ApprovalDecisionRequest,
) -> ApprovalDecisionResponse:
    try:
        return task_service.decide_approval(
            approval_id,
            approved=request.approved,
            decided_by=request.decided_by,
            reason=request.reason,
        )
    except ValueError as exc:
        detail = str(exc)
        status_code = 404 if "not found" in detail.lower() else 400
        raise HTTPException(status_code=status_code, detail=detail) from exc


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
