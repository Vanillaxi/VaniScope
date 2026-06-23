from __future__ import annotations

import json
from pathlib import Path

import pytest

from webscoper.api.task_service import TaskService
from webscoper.runtime.control import TaskControlStore
from webscoper.runtime.inspector.graph import RuntimeGraphBuilder
from webscoper.runtime.inspector.loader import RunArtifactLoader
from webscoper.runtime.llm.budget import (
    BudgetApprovalRequired,
    BudgetHardLimitExceeded,
    build_estimate,
    decide_budget,
)
from webscoper.runtime.llm.client import BaseLLMClient
from webscoper.runtime.llm.router import AuditedBudgetedLLMClient
from webscoper.runtime.safety.approvals import ApprovalStore
from webscoper.schemas.llm import LLMMessage, LLMRequest, LLMResponse
from webscoper.schemas.runtime import BudgetContext


class RecordingClient(BaseLLMClient):
    def __init__(self) -> None:
        self.requests: list[LLMRequest] = []

    async def generate(self, request: LLMRequest) -> LLMResponse:
        self.requests.append(request)
        return LLMResponse(content="ok", model=request.model)


def test_budget_below_soft_limit_allowed() -> None:
    decision = decide_budget(
        BudgetContext(),
        build_estimate(
            prompt_tokens_next_call=100,
            max_completion_tokens_next_call=100,
            prompt_tokens_so_far=0,
            completion_tokens_so_far=0,
            llm_calls_so_far=0,
        ),
    )

    assert decision == "allowed"


def test_budget_above_soft_limit_warns_without_stopping() -> None:
    decision = decide_budget(
        BudgetContext(soft_prompt_tokens_per_task=100, approval_prompt_tokens_per_task=500),
        build_estimate(
            prompt_tokens_next_call=150,
            max_completion_tokens_next_call=10,
            prompt_tokens_so_far=0,
            completion_tokens_so_far=0,
            llm_calls_so_far=0,
        ),
    )

    assert decision == "warning"


@pytest.mark.asyncio
async def test_budget_approval_required_creates_pending_approval(tmp_path: Path) -> None:
    class ExplodingClient(BaseLLMClient):
        async def generate(self, request: LLMRequest) -> LLMResponse:
            raise AssertionError("approval should pause before the client is called")

    approvals = ApprovalStore()
    control = TaskControlStore()
    client = AuditedBudgetedLLMClient(
        ExplodingClient(),
        provider="mock",
        model="mock",
        mode="real",
        audit_path=tmp_path / "llm_calls.jsonl",
        task_id="budget_task",
        purpose="planner",
        budget=BudgetContext(
            soft_prompt_tokens_per_task=10,
            approval_prompt_tokens_per_task=20,
            hard_prompt_tokens_per_task=500,
            max_prompt_tokens_per_call=1000,
        ),
        approval_store=approvals,
        control_store=control,
    )

    with pytest.raises(BudgetApprovalRequired):
        await client.generate(
            LLMRequest(messages=[LLMMessage(role="user", content="x" * 200)])
        )

    pending = approvals.list_for_task("budget_task")
    assert pending[0].metadata["approval_type"] == "llm_budget"
    assert pending[0].status == "pending"
    assert (tmp_path / "budget_decisions.jsonl").exists()
    audit = json.loads((tmp_path / "llm_calls.jsonl").read_text(encoding="utf-8"))
    assert audit["status"] == "skipped"
    assert audit["budget_decision"] == "approval_required"
    assert "api_key" not in audit


@pytest.mark.asyncio
async def test_continue_once_allows_one_budget_gated_call(tmp_path: Path) -> None:
    approvals = ApprovalStore()
    control = TaskControlStore()
    inner = RecordingClient()
    client = AuditedBudgetedLLMClient(
        inner,
        provider="mock",
        model="mock",
        mode="real",
        audit_path=tmp_path / "llm_calls.jsonl",
        task_id="continue_once_task",
        purpose="planner",
        budget=BudgetContext(
            soft_prompt_tokens_per_task=10,
            approval_prompt_tokens_per_task=20,
            hard_prompt_tokens_per_task=500,
            max_prompt_tokens_per_call=1000,
        ),
        approval_store=approvals,
        control_store=control,
    )

    request = LLMRequest(messages=[LLMMessage(role="user", content="x" * 200)])
    with pytest.raises(BudgetApprovalRequired):
        await client.generate(request)

    control.resolve_budget_approval("continue_once_task", continue_once=True)
    response = await client.generate(request)

    assert response.content == "ok"
    assert len(inner.requests) == 1
    assert not control.get("continue_once_task").budget_override


@pytest.mark.asyncio
async def test_continue_for_task_suppresses_approval_until_hard_limit(tmp_path: Path) -> None:
    control = TaskControlStore()
    control.resolve_budget_approval("task_budget_override", continue_for_task=True)
    inner = RecordingClient()
    client = AuditedBudgetedLLMClient(
        inner,
        provider="mock",
        model="mock",
        mode="real",
        audit_path=tmp_path / "llm_calls.jsonl",
        task_id="task_budget_override",
        purpose="planner",
        budget=BudgetContext(
            soft_prompt_tokens_per_task=10,
            approval_prompt_tokens_per_task=20,
            hard_prompt_tokens_per_task=500,
            max_prompt_tokens_per_call=1000,
        ),
        approval_store=ApprovalStore(),
        control_store=control,
    )

    await client.generate(LLMRequest(messages=[LLMMessage(role="user", content="x" * 200)]))

    assert len(inner.requests) == 1
    with pytest.raises(BudgetHardLimitExceeded):
        await client.generate(
            LLMRequest(messages=[LLMMessage(role="user", content="x" * 5000)])
        )


@pytest.mark.asyncio
async def test_continue_with_compaction_applies_aggressive_compaction(tmp_path: Path) -> None:
    control = TaskControlStore()
    control.resolve_budget_approval("compact_task", continue_with_compaction=True)
    inner = RecordingClient()
    client = AuditedBudgetedLLMClient(
        inner,
        provider="mock",
        model="mock",
        mode="real",
        audit_path=tmp_path / "llm_calls.jsonl",
        task_id="compact_task",
        purpose="planner",
        budget=BudgetContext(
            soft_prompt_tokens_per_task=10,
            approval_prompt_tokens_per_task=20,
            hard_prompt_tokens_per_task=1000,
            max_prompt_tokens_per_call=400,
        ),
        approval_store=ApprovalStore(),
        control_store=control,
    )

    await client.generate(LLMRequest(messages=[LLMMessage(role="user", content="x" * 1200)]))

    assert "[...prompt context compacted...]" in inner.requests[0].messages[0].content


@pytest.mark.asyncio
async def test_hard_per_call_limit_compacts_before_hard_failure(tmp_path: Path) -> None:
    events: list[str] = []
    client = AuditedBudgetedLLMClient(
        RecordingClient(),
        provider="mock",
        model="mock",
        mode="real",
        audit_path=tmp_path / "llm_calls.jsonl",
        task_id="hard_context_task",
        purpose="planner",
        budget=BudgetContext(
            hard_prompt_tokens_per_task=1000,
            max_prompt_tokens_per_call=40,
            enable_auto_compaction=True,
        ),
        event_sink=lambda kind, _message, _payload: events.append(kind),
    )

    with pytest.raises(BudgetHardLimitExceeded):
        await client.generate(
            LLMRequest(messages=[LLMMessage(role="user", content="x" * 10000)])
        )

    assert "budget_compaction_started" in events
    assert "budget_compaction_finished" in events
    assert "budget_hard_limit_exceeded" in events


def test_stop_and_summarize_without_evidence_writes_minimal_report(tmp_path: Path) -> None:
    service = TaskService(runs_dir=tmp_path / "runs", persistence_path=tmp_path / "db.sqlite")
    task_id = "task_no_evidence"
    service._run_dir(task_id).mkdir(parents=True)

    response = service.stop_and_summarize_task(task_id)

    report = (service._run_dir(task_id) / "final_report.md").read_text(encoding="utf-8")
    assert response.status == "succeeded_partial"
    assert "Task stopped before enough evidence was collected." in report
    assert "user_control.jsonl" in service.get_task_status(task_id).artifacts


def test_stop_and_summarize_with_evidence_writes_partial_report(tmp_path: Path) -> None:
    service = TaskService(runs_dir=tmp_path / "runs", persistence_path=tmp_path / "db.sqlite")
    task_id = "task_with_evidence"
    run_dir = service._run_dir(task_id)
    run_dir.mkdir(parents=True)
    (run_dir / "evidence.jsonl").write_text(
        json.dumps(
            {
                "evidence_id": "ev_001",
                "kind": "text_excerpt",
                "text": "Collected evidence before stopping.",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    response = service.stop_and_summarize_task(task_id)

    report = (run_dir / "final_report.md").read_text(encoding="utf-8")
    assert response.status == "succeeded_partial"
    assert "Task was stopped by user" in report
    assert "Collected evidence before stopping." in report


def test_control_store_appends_jsonl_history(tmp_path: Path) -> None:
    control = TaskControlStore()
    path = tmp_path / "user_control.jsonl"

    control.request("task_control", "pause")
    control.write_jsonl("task_control", path)
    control.request("task_control", "resume")
    control.write_jsonl("task_control", path)

    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 2
    assert rows[0]["pause_requested"] is True
    assert rows[1]["pause_requested"] is False


def test_graph_includes_budget_and_user_control_nodes(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    run_dir = runs_dir / "graph_task"
    run_dir.mkdir(parents=True)
    (run_dir / "events.jsonl").write_text(
        json.dumps(
            {
                "event_id": "evt_stop",
                "task_id": "graph_task",
                "kind": "user_stop_requested",
                "message": "User requested stop",
                "created_at": "2026-06-22T00:00:00+00:00",
                "payload": {"run_id": "graph_task"},
            }
        )
        + "\n"
        + json.dumps(
            {
                "event_id": "evt_report",
                "task_id": "graph_task",
                "kind": "partial_report_generated",
                "message": "Partial report generated",
                "created_at": "2026-06-22T00:00:01+00:00",
                "payload": {"run_id": "graph_task"},
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (run_dir / "budget_decisions.jsonl").write_text(
        json.dumps(
            {
                "timestamp": "2026-06-22T00:00:00+00:00",
                "decision": "approval_required",
                "estimated_prompt_tokens": 50001,
                "approval_threshold": 50000,
            }
        )
        + "\n",
        encoding="utf-8",
    )

    graph = RuntimeGraphBuilder(RunArtifactLoader(runs_dir, "graph_task")).build_graph_response()

    labels = {node.label for node in graph.nodes}
    assert "Budget Approval" in labels
    assert "User Stop" in labels
    assert "Partial Report" in labels
