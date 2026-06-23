from __future__ import annotations

from webscoper.api.schemas import ApprovalDecisionResponse
from webscoper.runtime.safety.approvals import ApprovalStoreError
from webscoper.schemas.runtime import TaskResumeResult
from webscoper.schemas.workflow import LangGraphResumeResult


def decide_approval(
    service,
    approval_id: str,
    approved: bool,
    decided_by: str,
    reason: str | None = None,
    option: str | None = None,
) -> ApprovalDecisionResponse:
    try:
        approval = service.approval_store.decide(
            approval_id,
            approved=approved,
            decided_by=decided_by,
            reason=reason,
        )
    except ApprovalStoreError as exc:
        raise ValueError(str(exc)) from exc

    run_dir = service._run_dir(approval.task_id)
    resume_result: TaskResumeResult | LangGraphResumeResult | None = None
    try:
        service.approval_store.write_jsonl_for_task(
            approval.task_id,
            run_dir / "approvals.jsonl",
        )
        service.approval_store.write_risk_report(
            approval.task_id,
            run_dir / "risk_report.json",
        )
        service._publish_task_event(
            approval.task_id,
            "approval_decided",
            "Approval decision recorded",
            {"approval_request": approval.model_dump(mode="json")},
        )
        service._publish_task_event(
            approval.task_id,
            "approval_resolved",
            "Approval resolved",
            {
                "approval_request": approval.model_dump(mode="json"),
                "approved": approved,
            },
        )
    except Exception:
        pass

    if approval.metadata.get("approval_type") == "llm_budget":
        resume_result = _resolve_budget_approval(
            service,
            approval=approval,
            approved=approved,
            option=option,
        )
        return ApprovalDecisionResponse(approval=approval, resume_result=resume_result)

    if approved:
        resume_result = service.resume_langgraph_after_approval(
            approval_id,
            approval.decision,
        )
    else:
        pending = service.pending_manager.pop_by_approval_id(approval_id)
        if pending is not None:
            service.pending_manager.write_jsonl(
                approval.task_id,
                run_dir / "pending.jsonl",
            )
        service._set_task_state(
            approval.task_id,
            "rejected",
            "Approval rejected; task will not resume.",
        )
        service._publish_task_event(
            approval.task_id,
            "task_rejected",
            "Approval rejected; task will not resume",
            {"approval_request": approval.model_dump(mode="json")},
        )
        resume_result = TaskResumeResult(
            task_id=approval.task_id,
            approval_id=approval_id,
            resumed=False,
            status="rejected",
            message="Approval rejected; task will not resume.",
            error=None,
        )
    return ApprovalDecisionResponse(approval=approval, resume_result=resume_result)


def _resolve_budget_approval(
    service,
    *,
    approval,
    approved: bool,
    option: str | None,
) -> TaskResumeResult:
    task_id = approval.task_id
    selected = option or ("continue_once" if approved else "cancel_task")
    if selected == "continue_once" and approved:
        service.control_store.resolve_budget_approval(task_id, continue_once=True)
        service._set_task_state(task_id, "running", None)
        message = "Budget approval resolved for one LLM call."
    elif selected == "continue_for_task" and approved:
        service.control_store.resolve_budget_approval(task_id, continue_for_task=True)
        service._set_task_state(task_id, "running", None)
        message = "Budget approval resolved for this task."
    elif selected == "continue_with_compaction" and approved:
        service.control_store.resolve_budget_approval(
            task_id,
            continue_with_compaction=True,
        )
        service._set_task_state(task_id, "running", None)
        message = "Budget approval resolved with aggressive compaction."
    elif selected == "stop_and_summarize":
        response = service.stop_and_summarize_task(task_id)
        message = response.message
    else:
        response = service.cancel_task(task_id)
        message = response.message
    run_dir = service._run_dir(task_id)
    service.control_store.write_jsonl(task_id, run_dir / "user_control.jsonl")
    service._publish_task_event(
        task_id,
        "budget_approval_resolved",
        "LLM budget approval resolved",
        {
            "approval_id": approval.approval_id,
            "approved": approved,
            "option": selected,
        },
    )
    request = service._task_requests.get(task_id)
    if approved and selected.startswith("continue") and request is not None:
        import asyncio
        import threading

        threading.Thread(
            target=lambda: asyncio.run(service._run_async_task(task_id, request)),
            daemon=True,
        ).start()
    return TaskResumeResult(
        task_id=task_id,
        approval_id=approval.approval_id,
        resumed=approved and selected.startswith("continue"),
        status=service.get_task_status(task_id).status,
        message=message,
        error=None,
    )
