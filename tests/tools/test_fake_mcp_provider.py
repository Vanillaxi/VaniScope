from __future__ import annotations

import pytest

from webscoper.tools.gateway import FakeMCPToolProvider, ToolInvocationRequest


@pytest.mark.asyncio
async def test_fake_mcp_provider_is_deterministic() -> None:
    provider = FakeMCPToolProvider()

    echo = await provider.invoke(
        ToolInvocationRequest(
            task_id="task",
            tool_name="fake_mcp_echo",
            arguments={"text": "hello"},
        )
    )
    time = await provider.invoke(
        ToolInvocationRequest(task_id="task", tool_name="fake_mcp_get_time")
    )
    doc = await provider.invoke(
        ToolInvocationRequest(
            task_id="task",
            tool_name="fake_mcp_fetch_doc",
            arguments={"topic": "gateway"},
        )
    )

    assert echo.output == {"text": "hello"}
    assert time.output == {"iso_time": "2026-01-01T00:00:00+00:00"}
    assert doc.output["content"] == "Fake MCP documentation for gateway."
