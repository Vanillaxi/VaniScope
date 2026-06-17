from __future__ import annotations

from webscoper.runtime.context import WebAgentContext
from webscoper.runtime.tool_executor import LocalToolExecutor
from webscoper.schemas.plan import ExecutionLoopResult, ExecutionPlan
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
    ) -> ExecutionLoopResult:
        transcript = context.transcript_store
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
