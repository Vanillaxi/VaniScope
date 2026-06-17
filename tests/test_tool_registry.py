from __future__ import annotations

from webscoper.tools.registry import create_default_tool_registry


def test_default_tool_registry_snapshot_and_search() -> None:
    registry = create_default_tool_registry()

    snapshot = registry.snapshot()
    core_tool_ids = {tool.tool_id for tool in snapshot.core_tools}
    lazy_tool_ids = {tool.tool_id for tool in snapshot.lazy_tools}
    search_result = registry.search("github issue")
    search_tool_ids = {tool.tool_id for tool in search_result.matches}

    assert "browser_open_observe" in core_tool_ids
    assert "browser_click_intent" in core_tool_ids
    assert "github_fetch_issue" in lazy_tool_ids
    assert "github_fetch_issue" in search_tool_ids
