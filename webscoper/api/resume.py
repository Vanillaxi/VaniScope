from __future__ import annotations

from webscoper.runtime.execution.handler import WebAgentExecutionHandler
from webscoper.schemas.task import TaskSpec
from webscoper.schemas.workflow import LangGraphResumeResult


def resume_langgraph_after_approval(
    service,
    approval_id: str,
    decision,
) -> LangGraphResumeResult:
    approval = service.approval_store.get(approval_id)
    if approval is None:
        return LangGraphResumeResult(
            task_id="unknown",
            approval_id=approval_id,
            resumed=False,
            status="failed",
            message="Approval request not found.",
            error=f"Approval request not found: {approval_id}",
        )
    if decision is None:
        return LangGraphResumeResult(
            task_id=approval.task_id,
            approval_id=approval_id,
            resumed=False,
            status="failed",
            message="Approval decision missing.",
            error="Approval decision missing.",
        )

    task_id = approval.task_id
    state = service._task_states.get(task_id)
    thread_id = state.thread_id if state is not None else task_id
    adapter = service._langgraph_adapters.get(task_id)
    if adapter is None:
        result = LangGraphResumeResult(
            task_id=task_id,
            approval_id=approval_id,
            resumed=False,
            status="failed",
            message="No LangGraph adapter found for approval.",
            error="LangGraph interrupted tasks can only resume in the current process.",
            metadata={"thread_id": thread_id},
        )
        service._set_task_state(task_id, "failed", result.error)
        service._publish_task_event(
            task_id,
            "langgraph_resume_failed",
            "LangGraph resume failed",
            result.model_dump(mode="json"),
        )
        service._publish_task_event(
            task_id,
            "task_failed",
            "Task failed while resuming LangGraph workflow",
            result.model_dump(mode="json"),
        )
        return result

    resume_payload = adapter.approval_bridge.build_resume_payload(
        approval_id=approval_id,
        approved=decision.approved,
        decided_by=decision.decided_by,
        reason=decision.reason,
    )
    service._set_task_state(task_id, "resuming", None)
    service._publish_task_event(
        task_id,
        "langgraph_resumed",
        "LangGraph resume command submitted",
        {
            "approval_id": approval_id,
            "thread_id": thread_id,
            "resume_payload": resume_payload.model_dump(mode="json"),
        },
    )
    pending = service.pending_manager.get_by_approval_id(approval_id)
    service._publish_task_event(
        task_id,
        "task_resumed",
        "Task resumed after approval",
        {
            "approval_id": approval_id,
            "thread_id": thread_id,
            "pending_tool_call": pending.model_dump(mode="json")
            if pending is not None
            else None,
        },
    )

    result = adapter.resume(
        task_id=task_id,
        thread_id=thread_id or task_id,
        resume_payload=resume_payload,
    )
    service._set_task_state(task_id, result.status, result.error)
    service._write_task_artifacts(task_id)
    if result.resumed:
        service._langgraph_adapters.pop(task_id, None)
    else:
        service._publish_task_event(
            task_id,
            "langgraph_resume_failed",
            "LangGraph resume failed",
            result.model_dump(mode="json"),
        )
        service._publish_task_event(
            task_id,
            "task_failed",
            "Task failed while resuming LangGraph workflow",
            result.model_dump(mode="json"),
        )
    return result


def run_langgraph_workflow(
    service,
    handler: WebAgentExecutionHandler,
    task: TaskSpec,
    task_id: str,
):
    try:
        from webscoper.workflows.langgraph_adapter import LangGraphWorkflowAdapter
    except ImportError as exc:
        raise RuntimeError(
            "LangGraph workflow requested but langgraph is not installed"
        ) from exc
    adapter = LangGraphWorkflowAdapter(handler)
    service._langgraph_adapters[task_id] = adapter
    return adapter.run(task)
