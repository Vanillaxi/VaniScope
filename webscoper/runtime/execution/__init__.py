"""Execution orchestration, planning, validation, and tool execution."""


def __getattr__(name: str):
    if name in {"WebAgentExecutionHandler", "WebAgentRuntimeComponents"}:
        from webscoper.runtime.execution.handler import (
            WebAgentExecutionHandler,
            WebAgentRuntimeComponents,
        )

        return {
            "WebAgentExecutionHandler": WebAgentExecutionHandler,
            "WebAgentRuntimeComponents": WebAgentRuntimeComponents,
        }[name]
    raise AttributeError(name)
