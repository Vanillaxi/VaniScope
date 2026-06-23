from __future__ import annotations

import json
from pathlib import Path

import pytest

from webscoper.api import approvals as approvals_module
from webscoper.api.schemas import TaskCreateRequest
from webscoper.api.task_service import TaskService
from webscoper.runtime.llm.client import BaseLLMClient, LLMProviderTimeoutError
from webscoper.runtime.llm.router import AuditedBudgetedLLMClient, LLMTimeoutApprovalRequired
from webscoper.runtime.safety.approvals import ApprovalStore
from webscoper.schemas.llm import LLMMessage, LLMRequest, LLMResponse
from webscoper.schemas.runtime import BudgetContext


class TimeoutThenSuccessClient(BaseLLMClient):
    def __init__(self) -> None:
        self.calls = 0

    async def generate(self, request: LLMRequest) -> LLMResponse:
        self.calls += 1
        if self.calls == 1:
            raise LLMProviderTimeoutError("The read operation timed out")
        return LLMResponse(content="ok after retry", model=request.model)


class AlwaysTimeoutClient(BaseLLMClient):
    def __init__(self) -> None:
        self.calls = 0

    async def generate(self, request: LLMRequest) -> LLMResponse:
        self.calls += 1
        raise LLMProviderTimeoutError("The read operation timed out")


@pytest.mark.asyncio
async def test_llm_timeout_retries_once_and_records_success(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def no_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr("webscoper.runtime.llm.router.asyncio.sleep", no_sleep)
    events: list[tuple[str, dict]] = []
    inner = TimeoutThenSuccessClient()
    client = AuditedBudgetedLLMClient(
        inner,
        provider="mock",
        model="slow-model",
        mode="real",
        audit_path=tmp_path / "llm_calls.jsonl",
        task_id="timeout_retry_task",
        purpose="planner",
        budget=BudgetContext(max_llm_retries_per_call=1, retry_on_llm_timeout=True),
        event_sink=lambda kind, _message, payload: events.append((kind, payload)),
    )

    response = await client.generate(
        LLMRequest(messages=[LLMMessage(role="user", content="hello")])
    )

    assert response.content == "ok after retry"
    assert inner.calls == 2
    event_kinds = [kind for kind, _payload in events]
    assert "llm_retry_scheduled" in event_kinds
    assert "llm_retry_started" in event_kinds
    assert "llm_retry_finished" in event_kinds
    failed_calls = [
        payload
        for kind, payload in events
        if kind == "llm_call_finished" and payload["status"] == "failed"
    ]
    assert failed_calls[0]["error_type"] == "LLM_PROVIDER_TIMEOUT"
    assert failed_calls[0]["retryable"] is True
    records = [
        json.loads(line)
        for line in (tmp_path / "llm_calls.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert records[0]["status"] == "failed"
    assert records[0]["error_type"] == "LLM_PROVIDER_TIMEOUT"
    assert records[0]["retryable"] is True
    assert records[1]["status"] == "success"


@pytest.mark.asyncio
async def test_llm_timeout_after_retry_creates_pending_approval(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def no_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr("webscoper.runtime.llm.router.asyncio.sleep", no_sleep)
    approvals = ApprovalStore()
    events: list[str] = []
    inner = AlwaysTimeoutClient()
    client = AuditedBudgetedLLMClient(
        inner,
        provider="qwen",
        model="qwen-plus",
        mode="real",
        audit_path=tmp_path / "llm_calls.jsonl",
        task_id="timeout_approval_task",
        purpose="planner",
        budget=BudgetContext(max_llm_retries_per_call=1, retry_on_llm_timeout=True),
        event_sink=lambda kind, _message, _payload: events.append(kind),
        approval_store=approvals,
        fallback_model="qwen-turbo",
        user_goal="collect evidence",
    )

    with pytest.raises(LLMTimeoutApprovalRequired) as raised:
        await client.generate(
            LLMRequest(messages=[LLMMessage(role="user", content="hello")])
        )

    pending = approvals.list_for_task("timeout_approval_task")
    assert raised.value.approval_id == pending[0].approval_id
    assert pending[0].status == "pending"
    assert pending[0].metadata["approval_type"] == "llm_timeout"
    assert pending[0].metadata["fallback_model"] == "qwen-turbo"
    assert pending[0].metadata["suggested_options"] == [
        "retry_same_model",
        "retry_with_faster_model",
        "stop_and_summarize",
        "cancel_task",
    ]
    assert "approval_required" in events
    records = [
        json.loads(line)
        for line in (tmp_path / "llm_calls.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert [record["status"] for record in records] == ["failed", "failed"]
    assert all(record["error_type"] == "LLM_PROVIDER_TIMEOUT" for record in records)


def test_llm_timeout_fallback_approval_updates_request_and_restarts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = TaskService(runs_dir=tmp_path / "runs", persistence_path=tmp_path / "db.sqlite")
    task_id = "timeout_fallback_task"
    service._run_dir(task_id).mkdir(parents=True)
    service._task_requests[task_id] = TaskCreateRequest(
        url="https://example.com",
        goal="Collect evidence",
        planner="real_llm",
        model="slow-model",
    )
    restarted: list[TaskCreateRequest] = []

    def fake_restart(_service, _task_id: str, request: TaskCreateRequest) -> None:
        restarted.append(request)

    monkeypatch.setattr(approvals_module, "_restart_task", fake_restart)
    approval = service.approval_store.create_request(
        task_id=task_id,
        reason="The LLM provider did not respond before the timeout.",
        risk_level="low",
        metadata={
            "approval_type": "llm_timeout",
            "provider": "qwen",
            "model": "slow-model",
            "fallback_model": "fast-model",
        },
    )

    response = service.decide_approval(
        approval.approval_id,
        approved=True,
        decided_by="test",
        option="retry_with_faster_model",
    )

    assert response.resume_result is not None
    assert response.resume_result.resumed is True
    assert service._task_requests[task_id].model == "fast-model"
    assert restarted[0].model == "fast-model"
    events = service.event_store.list_events(task_id)
    assert any(event.kind == "llm_fallback_model_selected" for event in events)
