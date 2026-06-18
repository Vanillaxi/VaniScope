from __future__ import annotations

from pathlib import Path

from webscoper.runtime.artifacts.pipeline import persist_evidence_and_report
from webscoper.runtime.context import WebAgentContext
from webscoper.runtime.evidence import EvidenceStore
from webscoper.runtime.execution import WebAgentExecutionHandler
from webscoper.runtime.execution_loop import AgentExecutionLoop
from webscoper.runtime.tool_executor import LocalToolExecutor
from webscoper.runtime.trace import TraceRecorder
from webscoper.runtime.transcript import TranscriptStore
from webscoper.schemas.context import RuntimeState, WebAgentContextSnapshot
from webscoper.schemas.plan import ExecutionPlan, PlannedStep
from webscoper.schemas.risk import TaskResumeResult
from webscoper.schemas.task import TaskSpec
from webscoper.schemas.tool_call import ToolCall
from webscoper.schemas.workflow import LangGraphResumeResult
from webscoper.browser.tool_runtime import StatefulBrowserToolRuntime
from webscoper.tools.registry import create_default_tool_registry


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


async def resume_after_approval(service, approval_id: str) -> TaskResumeResult:
    pending = service.pending_manager.pop_by_approval_id(approval_id)
    approval = service.approval_store.get(approval_id)
    if approval is None:
        return TaskResumeResult(
            task_id="unknown",
            approval_id=approval_id,
            resumed=False,
            status="failed",
            message="Approval request not found.",
            error=f"Approval request not found: {approval_id}",
        )
    task_id = approval.task_id
    if pending is None:
        return TaskResumeResult(
            task_id=task_id,
            approval_id=approval_id,
            resumed=False,
            status=service.get_task_status(task_id).status,
            message="No pending tool call found for approval.",
            error=None,
        )

    service._set_task_state(task_id, "resuming", None)
    service._publish_task_event(
        task_id,
        "task_resumed",
        "Task resumed after approval",
        {"approval_id": approval_id, "pending_tool_call": pending.model_dump(mode="json")},
    )

    try:
        context = context_from_pending(pending)
        browser_runtime = StatefulBrowserToolRuntime(
            trace_recorder=context.trace_recorder,
        )
        tool_executor = LocalToolExecutor(
            tool_registry=create_default_tool_registry(),
            browser_runtime=browser_runtime,
            approval_store=service.approval_store,
            pending_manager=service.pending_manager,
            event_sink=service._make_event_sink(task_id),
        )
        execution_loop = AgentExecutionLoop(
            tool_executor=tool_executor,
            event_sink=service._make_event_sink(task_id),
            approval_override_id=approval_id,
        )
        await browser_runtime.start()
        try:
            resume_url = resume_url_from_pending(pending)
            if resume_url is not None:
                await browser_runtime.open_observe(resume_url)
            context.transcript_store.append(
                "task_resumed",
                {
                    "approval_id": approval_id,
                    "pending_tool_call": pending.model_dump(mode="json"),
                },
            )
            plan = ExecutionPlan(
                plan_id=f"resume_{pending.pending_id}",
                task_id=context.task.task_id,
                steps=[
                    PlannedStep(
                        step_id="resume_step_001",
                        tool_call=ToolCall(
                            call_id=pending.tool_call_id or "resume_call_001",
                            tool_id=pending.tool_name,
                            arguments=pending.arguments,
                            reason=pending.reason,
                        ),
                        reason=pending.reason,
                        expected_outcome="Approved pending tool call completes.",
                    )
                ],
            )
            loop_result = await execution_loop.run(
                context,
                plan,
                record_plan_built=False,
            )
            if loop_result.status != "success":
                raise RuntimeError(
                    f"{loop_result.error_type or 'RESUME_FAILED'}: "
                    f"{loop_result.error_message or 'Resume failed.'}"
                )
            observation = browser_runtime.last_observation
            if observation is None:
                raise RuntimeError("Resume completed without a final observation.")
            context.state.status = "completed"
            persist_evidence_and_report(
                context,
                observation,
                service._make_event_sink(task_id),
            )
            context.transcript_store.append(
                "execution_completed",
                {
                    "task_id": context.task.task_id,
                    "run_id": context.run_id,
                    "run_dir": str(context.run_dir),
                    "state": context.state.model_dump(mode="json"),
                },
            )
            service._set_task_state(task_id, "succeeded", None)
            service._write_task_artifacts(task_id)
            service._publish_task_event(
                task_id,
                "task_finished",
                "Task resumed and finished",
                {"approval_id": approval_id, "status": "succeeded"},
            )
            return TaskResumeResult(
                task_id=task_id,
                approval_id=approval_id,
                resumed=True,
                status="succeeded",
                message="Task resumed and finished.",
                error=None,
            )
        finally:
            await browser_runtime.close()
    except Exception as exc:
        service._set_task_state(task_id, "failed", str(exc))
        service._write_task_artifacts(task_id)
        service._publish_task_event(
            task_id,
            "resume_failed",
            "Task resume failed",
            {"approval_id": approval_id, "error": str(exc)},
        )
        service._publish_task_event(
            task_id,
            "task_failed",
            "Task failed while resuming",
            {"approval_id": approval_id, "error": str(exc)},
        )
        return TaskResumeResult(
            task_id=task_id,
            approval_id=approval_id,
            resumed=False,
            status="failed",
            message="Task resume failed.",
            error=str(exc),
        )


def context_from_pending(pending) -> WebAgentContext:
    snapshot_payload = pending.metadata.get("context_snapshot")
    snapshot = WebAgentContextSnapshot.model_validate(snapshot_payload)
    task = TaskSpec.model_validate(snapshot.task.model_dump(mode="json"))
    run_dir = Path(snapshot.trace.run_dir)
    run_id = snapshot.trace.run_id
    return WebAgentContext(
        task=task,
        run_id=run_id,
        run_dir=run_dir,
        trace_recorder=TraceRecorder(run_dir=run_dir, run_id=run_id),
        transcript_store=TranscriptStore(run_dir=run_dir, run_id=run_id),
        evidence_store=EvidenceStore(run_dir / "evidence.jsonl"),
        version=snapshot.version,
        state=RuntimeState(status="resuming"),
    )


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


def resume_url_from_pending(pending) -> str | None:
    page_observation = pending.metadata.get("page_observation")
    if isinstance(page_observation, dict) and page_observation.get("url"):
        return str(page_observation["url"])
    snapshot = pending.metadata.get("context_snapshot")
    if isinstance(snapshot, dict):
        task = snapshot.get("task")
        if isinstance(task, dict) and task.get("target_url"):
            return str(task["target_url"])
    return None
