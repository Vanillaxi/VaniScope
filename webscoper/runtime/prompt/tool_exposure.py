from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse

from webscoper.schemas.tool import ToolSpec
from webscoper.tools.registry import ToolRegistry


INITIAL_AUTO_EXPLORE_TOOLS = {
    "browser_open",
    "ask_human",
    "finish_task",
}
OBSERVED_AUTO_EXPLORE_TOOLS = {
    "browser_observe",
    "browser_click",
    "browser_scroll",
    "browser_wait",
    "browser_extract",
    "browser_screenshot",
    "ask_human",
    "finish_task",
}
INPUT_TOOLS = {"browser_type", "browser_select"}


@dataclass
class PromptToolSelection:
    available_tools: list[ToolSpec] = field(default_factory=list)
    hidden_tools: dict[str, str] = field(default_factory=dict)
    lazy_tools: list[ToolSpec] = field(default_factory=list)
    disabled_tools: dict[str, str] = field(default_factory=dict)

    @property
    def available_actions(self) -> list[str]:
        return [tool.tool_id for tool in self.available_tools]

    @property
    def lazy_tool_ids(self) -> list[str]:
        return [tool.tool_id for tool in self.lazy_tools]

    def model_dump(self) -> dict[str, Any]:
        return {
            "available_actions": self.available_actions,
            "hidden_tools": self.hidden_tools,
            "lazy_tools": self.lazy_tool_ids,
            "disabled_tools": self.disabled_tools,
        }


def select_prompt_tools(
    registry: ToolRegistry,
    *,
    context: Any,
    observation: Any | None = None,
) -> PromptToolSelection:
    task = context.task
    opened = observation is not None
    local_fixture = _is_local_fixture_task(task, observation)
    public_web = not local_fixture
    input_allowed = _input_tools_allowed(task, observation, local_fixture=local_fixture)
    stage_tools = _stage_tool_ids(task, opened=opened, input_allowed=input_allowed)
    selection = PromptToolSelection()

    for tool in registry.list_tools():
        reason = _policy_hidden_reason(
            tool,
            stage_tools=stage_tools,
            public_web=public_web,
            local_fixture=local_fixture,
            input_allowed=input_allowed,
            opened=opened,
        )
        if tool.exposure == "lazy" or tool.loading_mode == "lazy":
            selection.lazy_tools.append(tool)
        elif tool.exposure == "disabled" or not tool.enabled:
            selection.disabled_tools[tool.tool_id] = reason or "disabled/reserved"
        elif reason is not None:
            selection.hidden_tools[tool.tool_id] = reason
        else:
            selection.available_tools.append(tool)

    return selection


def tool_selection_markdown(selection: PromptToolSelection) -> str:
    lines = ["# Tool Exposure", "", "Available actions:"]
    if selection.available_actions:
        lines.extend(f"- {tool_id}" for tool_id in selection.available_actions)
    else:
        lines.append("- none")

    lines.extend(["", "Hidden tools:"])
    unavailable_tools = {**selection.hidden_tools, **selection.disabled_tools}
    if unavailable_tools:
        lines.extend(
            f"- {tool_id}: {reason}"
            for tool_id, reason in unavailable_tools.items()
        )
    else:
        lines.append("- none")

    lines.extend(["", "Lazy tools:"])
    if selection.lazy_tool_ids:
        lines.extend(f"- {tool_id}" for tool_id in selection.lazy_tool_ids)
    else:
        lines.append("- none")

    lines.extend(["", "Disabled tools:"])
    if selection.disabled_tools:
        lines.extend(
            f"- {tool_id}: {reason}"
            for tool_id, reason in selection.disabled_tools.items()
        )
    else:
        lines.append("- none")
    return "\n".join(lines)


def _stage_tool_ids(task: Any, *, opened: bool, input_allowed: bool) -> set[str]:
    if getattr(task, "mode", None) == "auto_explore" and getattr(
        task, "task_type", None
    ) == "browser_task":
        if not opened:
            return set(INITIAL_AUTO_EXPLORE_TOOLS)
        tool_ids = set(OBSERVED_AUTO_EXPLORE_TOOLS)
        if input_allowed:
            tool_ids.update(INPUT_TOOLS)
        return tool_ids

    if not opened:
        return set(INITIAL_AUTO_EXPLORE_TOOLS)
    tool_ids = set(OBSERVED_AUTO_EXPLORE_TOOLS)
    if input_allowed:
        tool_ids.update(INPUT_TOOLS)
    return tool_ids


def _policy_hidden_reason(
    tool: ToolSpec,
    *,
    stage_tools: set[str],
    public_web: bool,
    local_fixture: bool,
    input_allowed: bool,
    opened: bool,
) -> str | None:
    if tool.exposure == "disabled" or not tool.enabled:
        return "disabled/reserved"
    if tool.exposure == "compatibility" or tool.compatibility_wrapper:
        return "compatibility wrapper"
    if not tool.real_llm_prompt_allowed:
        return "not allowed in real LLM prompt"
    if tool.tool_id in INPUT_TOOLS and not input_allowed:
        if public_web:
            return "hidden on public web by default"
        return "hidden until local fixture form input is explicitly in scope"
    if public_web:
        if tool.public_web_exposure == "hidden":
            return "hidden on public web by policy"
        if tool.public_web_exposure == "approval_required":
            return "requires approval on public web"
    if local_fixture and tool.local_fixture_exposure == "hidden":
        return "hidden on local fixtures by policy"
    if tool.tool_id not in stage_tools:
        return (
            "not required before page is opened"
            if not opened
            else "not required for current browser state"
        )
    return None


def _input_tools_allowed(
    task: Any,
    observation: Any | None,
    *,
    local_fixture: bool,
) -> bool:
    if not local_fixture:
        return False
    safety = getattr(task, "safety", None)
    if bool(getattr(safety, "allow_sensitive_input", False)):
        return True
    tags = [str(tag).lower() for tag in getattr(task, "tags", [])]
    if any(tag in {"form", "fixture_form", "input"} for tag in tags):
        return True
    text = " ".join(
        str(value or "").lower()
        for value in (
            getattr(task, "raw_input", None),
            getattr(task, "goal", None),
            getattr(task, "query", None),
            getattr(task, "expected_output", None),
        )
    )
    return any(term in text for term in ("form", "fill", "type", "select", "input"))


def _is_local_fixture_task(task: Any, observation: Any | None) -> bool:
    observation_url = str(getattr(observation, "url", "") or "")
    return _is_local_fixture_url(observation_url) or _is_local_fixture_url(
        str(getattr(task, "target_url", "") or "")
    )


def _is_local_fixture_url(url: str) -> bool:
    if not url:
        return False
    parsed = urlparse(url)
    if parsed.scheme == "file":
        return True
    if parsed.scheme in {"http", "https"}:
        return parsed.hostname in {"localhost", "127.0.0.1", "::1"}
    return url.startswith("tests/fixtures/") or "/tests/fixtures/" in url
