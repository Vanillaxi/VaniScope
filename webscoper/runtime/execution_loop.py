from __future__ import annotations

from webscoper.runtime.context import WebAgentContext
from webscoper.runtime.tool_executor import LocalToolExecutor
from webscoper.schemas.plan import ExecutionLoopResult, ExecutionPlan
from webscoper.schemas.tool_call import ToolCall, ToolResult
from webscoper.schemas.tool_call import ToolExecutionRecord


class AgentExecutionLoop:
    def __init__(
        self,
        tool_executor: LocalToolExecutor,
    ) -> None:
        self.tool_executor = tool_executor

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
            tool_result = await self.tool_executor.execute(
                step.tool_call,
                context.snapshot(),
            )
            record = ToolExecutionRecord(call=step.tool_call, result=tool_result)
            records.append(record)
            transcript.append(
                "tool_call_completed",
                record.model_dump(mode="json"),
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


def _merge_final_output(final_output: dict, output: dict) -> None:
    if not output:
        return
    if "observation" in output:
        final_output["observation"] = output["observation"]
    if "visible_text_summary" in output:
        final_output["extract"] = output
    if "summary" in output:
        final_output["summary"] = output.get("summary")
        final_output["final_url"] = output.get("final_url")
        final_output["final_title"] = output.get("final_title")


def _record_evidence(
    context: WebAgentContext,
    step_id: str,
    tool_call: ToolCall,
    tool_result: ToolResult,
):
    evidence_store = context.evidence_store
    if evidence_store is None or tool_result.status not in {"success", "blocked"}:
        return None

    output = tool_result.output
    if tool_call.tool_id == "browser_open_observe":
        observation = output.get("observation")
        if isinstance(observation, dict):
            return evidence_store.add_item(
                kind="page_observation",
                source_url=_str_or_none(observation.get("url")),
                page_title=_str_or_none(observation.get("title")),
                text=_str_or_none(observation.get("visible_text_summary")),
                screenshot_path=_str_or_none(observation.get("screenshot_path")),
                trace_event_id=step_id,
                metadata={
                    "tool_id": tool_call.tool_id,
                    "call_id": tool_call.call_id,
                    "interactive_element_count": len(
                        observation.get("interactive_elements") or []
                    ),
                    "risk_signal_count": len(observation.get("risk_signals") or []),
                },
            )

    if tool_call.tool_id == "browser_click_intent":
        observation = output.get("observation")
        action_result = output.get("action_result")
        verification_result = output.get("verification_result")
        if isinstance(observation, dict):
            target_hint = _target_hint(tool_call, action_result)
            verified = (
                verification_result.get("satisfied")
                if isinstance(verification_result, dict)
                else None
            )
            return evidence_store.add_item(
                kind="action_result",
                source_url=_str_or_none(observation.get("url")),
                page_title=_str_or_none(observation.get("title")),
                text=_action_text(target_hint, verified, verification_result),
                screenshot_path=_str_or_none(observation.get("screenshot_path")),
                trace_event_id=step_id,
                metadata={
                    "tool_id": tool_call.tool_id,
                    "call_id": tool_call.call_id,
                    "target_hint": target_hint,
                    "verified": verified,
                },
            )

    if tool_call.tool_id == "browser_extract":
        return evidence_store.add_item(
            kind="text_excerpt",
            source_url=_str_or_none(output.get("url")),
            page_title=_str_or_none(output.get("title")),
            text=_str_or_none(output.get("visible_text_summary")),
            trace_event_id=step_id,
            metadata={
                "tool_id": tool_call.tool_id,
                "call_id": tool_call.call_id,
                "interactive_elements_count": output.get("interactive_elements_count"),
                "risk_signals_count": output.get("risk_signals_count"),
            },
        )

    return None


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
