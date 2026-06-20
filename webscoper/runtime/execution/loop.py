from __future__ import annotations

from webscoper.runtime.execution.context import WebAgentContext
from webscoper.runtime.execution.events import TaskEventSink
from webscoper.runtime.execution.results import merge_final_output, record_evidence
from webscoper.runtime.execution.tool_executor import LocalToolExecutor
from webscoper.schemas.tool import ExecutionLoopResult, ExecutionPlan
from webscoper.schemas.tool import ToolCall, ToolResult
from webscoper.schemas.tool import ToolExecutionRecord


class AgentExecutionLoop:
    def __init__(
        self,
        tool_executor: LocalToolExecutor,
        event_sink: TaskEventSink | None = None,
        approval_override_id: str | None = None,
    ) -> None:
        self.tool_executor = tool_executor
        self.event_sink = event_sink
        self.approval_override_id = approval_override_id

    async def run(
        self,
        context: WebAgentContext,
        plan: ExecutionPlan,
        record_plan_built: bool = True,
    ) -> ExecutionLoopResult:
        transcript = context.transcript_store
        if record_plan_built:
            transcript.append("plan_built", plan.model_dump(mode="json"))

        records: list[ToolExecutionRecord] = []
        final_output: dict = {}

        for index, step in enumerate(plan.steps, start=1):
            if index > context.task.budget.max_steps:
                result = ExecutionLoopResult(
                    task_id=context.task.task_id,
                    status="failed",
                    records=records,
                    final_output=final_output,
                    error_type="MAX_STEPS_EXCEEDED",
                    error_message="Execution plan exceeded task budget max_steps.",
                )
                transcript.append(
                    "execution_loop_failed",
                    result.model_dump(mode="json"),
                )
                return result

            transcript.append(
                "tool_call_started",
                {
                    "step": step.model_dump(mode="json"),
                    "call": step.tool_call.model_dump(mode="json"),
                },
            )
            self._emit(
                context,
                "tool_call_started",
                f"Tool call started: {step.tool_call.tool_id}",
                {
                    "step_id": step.step_id,
                    "tool_name": step.tool_call.tool_id,
                    "call_id": step.tool_call.call_id,
                },
            )
            tool_result = await self.tool_executor.execute(
                step.tool_call,
                context.snapshot(),
                approval_override_id=self.approval_override_id,
            )
            record = ToolExecutionRecord(call=step.tool_call, result=tool_result)
            records.append(record)
            transcript.append(
                "tool_call_completed",
                record.model_dump(mode="json"),
            )
            if tool_result.error_type == "RISK_APPROVAL_REQUIRED":
                transcript.append(
                    "approval_required",
                    {
                        "call": step.tool_call.model_dump(mode="json"),
                        "result": tool_result.model_dump(mode="json"),
                    },
                )
                transcript.append(
                    "task_paused",
                    {
                        "call": step.tool_call.model_dump(mode="json"),
                        "result": tool_result.model_dump(mode="json"),
                    },
                )
            elif tool_result.status == "blocked":
                transcript.append(
                    "risk_blocked",
                    {
                        "call": step.tool_call.model_dump(mode="json"),
                        "result": tool_result.model_dump(mode="json"),
                    },
                )
            self._emit(
                context,
                "tool_call_finished",
                f"Tool call finished: {step.tool_call.tool_id}",
                {
                    "step_id": step.step_id,
                    "tool_name": step.tool_call.tool_id,
                    "call_id": step.tool_call.call_id,
                    "ok": tool_result.status == "success",
                    "status": tool_result.status,
                    "error_type": tool_result.error_type,
                },
            )
            evidence_item = _record_evidence(
                context,
                step.step_id,
                step.tool_call,
                tool_result,
            )
            if evidence_item is not None:
                transcript.append(
                    "evidence_recorded",
                    evidence_item.model_dump(mode="json"),
                )
                self._emit(
                    context,
                    "evidence_added",
                    f"Evidence added: {evidence_item.evidence_id}",
                    {
                        "evidence_id": evidence_item.evidence_id,
                        "kind": evidence_item.kind,
                        "tool_name": step.tool_call.tool_id,
                    },
                )

            _merge_final_output(final_output, tool_result.output)

            if tool_result.status in {"failed", "blocked"}:
                result = ExecutionLoopResult(
                    task_id=context.task.task_id,
                    status="failed",
                    records=records,
                    final_output=final_output,
                    error_type=tool_result.error_type,
                    error_message=tool_result.error_message,
                )
                transcript.append(
                    "execution_loop_failed",
                    result.model_dump(mode="json"),
                )
                return result

        result = ExecutionLoopResult(
            task_id=context.task.task_id,
            status="success",
            records=records,
            final_output=final_output,
        )
        transcript.append("execution_loop_completed", result.model_dump(mode="json"))
        return result

    def _emit(
        self,
        context: WebAgentContext,
        kind: str,
        message: str,
        payload: dict | None = None,
    ) -> None:
        if self.event_sink is None:
            return
        try:
            event_payload = {"run_id": context.run_id}
            event_payload.update(payload or {})
            self.event_sink(kind, message, event_payload)
        except Exception:
            return


def _merge_final_output(final_output: dict, output: dict) -> None:
    merge_final_output(final_output, output)


def _record_evidence(
    context: WebAgentContext,
    step_id: str,
    tool_call: ToolCall,
    tool_result: ToolResult,
):
    return record_evidence(context, step_id, tool_call, tool_result)


def _target_hint(tool_call: ToolCall, action_result) -> str | None:
    if isinstance(action_result, dict):
        target = action_result.get("target")
        if isinstance(target, dict) and target.get("target_hint"):
            return str(target.get("target_hint"))
    action = tool_call.arguments.get("action")
    if isinstance(action, dict) and action.get("target_hint"):
        return str(action.get("target_hint"))
    return None


def _action_text(
    target_hint: str | None,
    verified,
    verification_result,
) -> str:
    parts = []
    if target_hint:
        parts.append(f"Clicked target: {target_hint}.")
    if verified is not None:
        parts.append(f"Verification satisfied: {bool(verified)}.")
    if isinstance(verification_result, dict) and verification_result.get("message"):
        parts.append(str(verification_result.get("message")))
    return " ".join(parts) if parts else "Browser action completed."


def _str_or_none(value) -> str | None:
    if value is None:
        return None
    return str(value)
