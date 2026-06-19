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
    except Exception:
        pass

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
