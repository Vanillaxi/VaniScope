from __future__ import annotations

from webscoper.runtime.llm_client import BaseLLMClient
from webscoper.runtime.tool_call_parser import ToolCallParser
from webscoper.schemas.context import WebAgentContextSnapshot
from webscoper.schemas.llm import LLMMessage, LLMRequest, LLMResponse, ParsedToolCalls
from webscoper.schemas.plan import ExecutionPlan, PlannedStep
from webscoper.schemas.prompt import PromptBuildResult


class LLMTaskPlanner:
    def __init__(
        self,
        llm_client: BaseLLMClient,
        parser: ToolCallParser | None = None,
    ) -> None:
        self.llm_client = llm_client
        self.parser = parser or ToolCallParser()
        self.last_request: LLMRequest | None = None
        self.last_response: LLMResponse | None = None
        self.last_parse_result: ParsedToolCalls | None = None

    async def build_plan(
        self,
        context: WebAgentContextSnapshot,
        prompt: PromptBuildResult,
    ) -> ExecutionPlan:
        request = LLMRequest(
            messages=[
                LLMMessage(role="system", content=prompt.prompt_text),
                LLMMessage(role="user", content=context.task.raw_input),
            ],
            model=_model_name(context.version.model),
            metadata={
                "task_id": context.task.task_id,
                "target_url": context.task.target_url,
                "action": (
                    context.task.action.model_dump(mode="json")
                    if context.task.action is not None
                    else None
                ),
            },
        )
        self.last_request = request
        response = await self.llm_client.generate(request)
        self.last_response = response
        parse_result = self.parser.parse(response.content)
        self.last_parse_result = parse_result

        if parse_result.status != "success":
            raise RuntimeError(
                f"{parse_result.error_type or 'TOOL_CALL_PARSE_FAILED'}: "
                f"{parse_result.error_message or 'Failed to parse tool calls.'}"
            )

        steps = [
            PlannedStep(
                step_id=f"step_{index:03d}",
                tool_call=tool_call,
                reason=tool_call.reason or f"Run tool {tool_call.tool_id}.",
            )
            for index, tool_call in enumerate(parse_result.tool_calls, start=1)
        ]
        return ExecutionPlan(
            plan_id=f"llm_plan_{context.task.task_id}",
            task_id=context.task.task_id,
            steps=steps,
        )


def _model_name(model: str | None) -> str:
    if model and model != "none":
        return model
    return "fake-llm"
