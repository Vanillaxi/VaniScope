from __future__ import annotations

from webscoper.runtime.llm.client import BaseLLMClient
from webscoper.runtime.execution.tool_call_parser import ToolCallParser
from webscoper.schemas.context import WebAgentContextSnapshot
from webscoper.schemas.llm import LLMMessage, LLMRequest, LLMResponse, ParsedToolCalls
from webscoper.schemas.plan import ExecutionPlan, PlannedStep
from webscoper.schemas.prompt import PromptBuildResult


class LLMTaskPlanner:
    def __init__(
        self,
        llm_client: BaseLLMClient,
        parser: ToolCallParser | None = None,
        repair_attempts: int = 0,
    ) -> None:
        self.llm_client = llm_client
        self.parser = parser or ToolCallParser()
        self.repair_attempts = max(0, repair_attempts)
        self.last_request: LLMRequest | None = None
        self.last_response: LLMResponse | None = None
        self.last_parse_result: ParsedToolCalls | None = None
        self.repair_requests: list[LLMRequest] = []
        self.repair_responses: list[LLMResponse] = []
        self.repair_parse_results: list[ParsedToolCalls] = []

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
            parse_result = await self._repair_tool_calls(
                context=context,
                prompt=prompt,
                previous_response=response,
                parse_result=parse_result,
            )

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

    async def _repair_tool_calls(
        self,
        context: WebAgentContextSnapshot,
        prompt: PromptBuildResult,
        previous_response: LLMResponse,
        parse_result: ParsedToolCalls,
    ) -> ParsedToolCalls:
        current_parse_result = parse_result
        current_response = previous_response
        for _ in range(self.repair_attempts):
            request = LLMRequest(
                messages=[
                    LLMMessage(role="system", content=_repair_system_prompt()),
                    LLMMessage(
                        role="user",
                        content=_repair_user_prompt(
                            prompt=prompt,
                            context=context,
                            previous_response=current_response,
                            parse_result=current_parse_result,
                        ),
                    ),
                ],
                model=_model_name(context.version.model),
                metadata={
                    "task_id": context.task.task_id,
                    "target_url": context.task.target_url,
                    "repair": True,
                },
            )
            self.repair_requests.append(request)
            current_response = await self.llm_client.generate(request)
            self.repair_responses.append(current_response)
            current_parse_result = self.parser.parse(current_response.content)
            self.repair_parse_results.append(current_parse_result)
            if current_parse_result.status == "success":
                return current_parse_result
        return current_parse_result


def _model_name(model: str | None) -> str:
    if model and model != "none":
        return model
    return "fake-llm"


def _repair_system_prompt() -> str:
    return (
        "The previous response could not be parsed as tool calls.\n"
        "Return only valid JSON with this shape:\n"
        "{\n"
        '  "tool_calls": [\n'
        "    {\n"
        '      "call_id": "call_001",\n'
        '      "tool_id": "...",\n'
        '      "arguments": {},\n'
        '      "reason": "..."\n'
        "    }\n"
        "  ]\n"
        "}\n"
        "Do not include markdown fences or prose."
    )


def _repair_user_prompt(
    prompt: PromptBuildResult,
    context: WebAgentContextSnapshot,
    previous_response: LLMResponse,
    parse_result: ParsedToolCalls,
) -> str:
    return (
        f"Task: {context.task.raw_input}\n\n"
        f"Target URL: {context.task.target_url}\n\n"
        f"Available planning prompt:\n{prompt.prompt_text}\n\n"
        f"Previous response:\n{previous_response.content}\n\n"
        f"Parse error type: {parse_result.error_type}\n"
        f"Parse error message: {parse_result.error_message}\n"
    )
