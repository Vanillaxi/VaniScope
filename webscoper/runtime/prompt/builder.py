from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from webscoper.schemas.artifact import ContextPack
from webscoper.schemas.runtime import WebAgentContextSnapshot
from webscoper.schemas.runtime import (
    AgentsMdInstruction,
    PromptBuildResult,
    RuntimeReminder,
    SkillPromptContext,
)
from webscoper.schemas.tool import ToolSpec
from webscoper.tools.registry import ToolRegistry


MAX_AGENTS_MD_FILES = 5
MAX_AGENTS_MD_CHARS = 8000
INITIAL_AUTO_EXPLORE_TOOLS = {"browser_open", "ask_human", "finish_task"}
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


class AgentsMdLoader:
    def __init__(self, include_global: bool = False) -> None:
        self.include_global = include_global

    def load(self, workspace: Path | None = None) -> list[AgentsMdInstruction]:
        instructions: list[AgentsMdInstruction] = []

        if self.include_global:
            global_path = Path.home() / ".vaniscope" / "AGENTS.md"
            instruction = _read_agents_md(global_path)
            if instruction is not None:
                instructions.append(instruction)

        if workspace is not None:
            start = workspace.parent if workspace.is_file() else workspace
            for path in _candidate_paths(start):
                if len(instructions) >= MAX_AGENTS_MD_FILES:
                    break
                instruction = _read_agents_md(path)
                if instruction is not None:
                    instructions.append(instruction)

        return instructions


class RuntimeReminderStore:
    def __init__(self) -> None:
        self._reminders: list[RuntimeReminder] = []

    def add(self, message: str, level: str = "info", source: str = "runtime") -> None:
        self._reminders.append(
            RuntimeReminder(message=message, level=level, source=source)
        )

    def list(self) -> list[RuntimeReminder]:
        return list(self._reminders)

    def render_xml(self) -> str:
        if not self._reminders:
            return ""

        return "\n".join(
            [
                (
                    f'<system-reminder level="{_xml_escape(reminder.level)}" '
                    f'source="{_xml_escape(reminder.source)}">\n'
                    f"{_xml_escape(reminder.message)}\n"
                    "</system-reminder>"
                )
                for reminder in self._reminders
            ]
        )


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
        lines.extend(f"- {tool_id}: {reason}" for tool_id, reason in unavailable_tools.items())
    else:
        lines.append("- none")

    lines.extend(["", "Lazy tools:"])
    if selection.lazy_tool_ids:
        lines.extend(f"- {tool_id}" for tool_id in selection.lazy_tool_ids)
    else:
        lines.append("- none")

    lines.extend(["", "Disabled tools:"])
    if selection.disabled_tools:
        lines.extend(f"- {tool_id}: {reason}" for tool_id, reason in selection.disabled_tools.items())
    else:
        lines.append("- none")
    return "\n".join(lines)


def _candidate_paths(start: Path) -> list[Path]:
    paths: list[Path] = []
    current = start.resolve()
    while True:
        paths.append(current / "AGENTS.md")
        if (current / ".git").exists() or current.parent == current:
            break
        current = current.parent
    return paths


def _read_agents_md(path: Path) -> AgentsMdInstruction | None:
    try:
        if not path.exists() or not path.is_file():
            return None
        content = path.read_text(encoding="utf-8")
    except Exception:
        return None

    if len(content) > MAX_AGENTS_MD_CHARS:
        content = content[:MAX_AGENTS_MD_CHARS].rstrip() + "\n<!-- truncated -->"

    return AgentsMdInstruction(source_path=str(path), content=content)


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


class DynamicPromptBuilder:
    def __init__(self, tool_registry: ToolRegistry) -> None:
        self.tool_registry = tool_registry

    def build(
        self,
        context: WebAgentContextSnapshot,
        agents_md_instructions: list[AgentsMdInstruction] | None = None,
        runtime_reminders: list[RuntimeReminder] | None = None,
        skill: SkillPromptContext | None = None,
        context_pack: ContextPack | None = None,
    ) -> PromptBuildResult:
        agents_md_instructions = agents_md_instructions or []
        runtime_reminders = runtime_reminders or []
        tool_selection = select_prompt_tools(
            self.tool_registry,
            context=context,
        )

        sections = {
            "identity": _identity_section(),
            "task": _task_section(context),
            "safety": _safety_section(context),
            "skill_instruction": _skill_instruction_section(skill),
            "permission_mode": context.safety.mode,
            "runtime_version": _runtime_version_section(context),
            "core_tools": _core_tools_section(tool_selection.available_tools),
            "lazy_tools": _lazy_tools_section(tool_selection.lazy_tools),
            "agents_md": _agents_md_section(agents_md_instructions),
            "runtime_reminders": _runtime_reminders_section(runtime_reminders),
            "output_rules": _output_rules_section(),
        }
        ordered_keys = [
            "identity",
            "task",
            "safety",
            "skill_instruction",
            "permission_mode",
            "runtime_version",
            "core_tools",
            "lazy_tools",
            "agents_md",
            "runtime_reminders",
            "output_rules",
        ]
        if context_pack is not None:
            sections["compacted_context"] = _compacted_context_section(context_pack)
            ordered_keys.insert(3, "compacted_context")
        prompt_text = "\n\n".join(sections[key] for key in ordered_keys)

        return PromptBuildResult(
            prompt_text=prompt_text,
            prompt_preview_text=tool_selection_markdown(tool_selection)
            + "\n\n"
            + prompt_text,
            sections=sections,
            loaded_agents_md_paths=[
                instruction.source_path for instruction in agents_md_instructions
            ],
            core_tool_ids=tool_selection.available_actions,
            lazy_tool_ids=tool_selection.lazy_tool_ids,
            available_actions=tool_selection.available_actions,
            hidden_tools=tool_selection.hidden_tools,
            disabled_tools=tool_selection.disabled_tools,
            skill=skill,
            compact_context_metadata=context_pack.model_dump(mode="json")
            if context_pack is not None
            else None,
        )


def _identity_section() -> str:
    return "# Identity\n\nYou are VaniScope, a browser agent runtime for public web tasks."


def _task_section(context: WebAgentContextSnapshot) -> str:
    task = context.task
    lines = [
        "# Task",
        "",
        f"- task_id: {task.task_id}",
        f"- raw_input: {task.raw_input}",
        f"- task_type: {task.task_type}",
        f"- skill_id: {task.skill_id or 'none'}",
        f"- target_url: {task.target_url}",
        f"- query: {task.query or 'none'}",
        f"- research_goal: {task.research_goal or 'none'}",
        f"- expected_output: {task.expected_output or 'none'}",
        f"- language: {task.language}",
        f"- require_evidence: {task.require_evidence}",
        f"- tags: {', '.join(task.tags) if task.tags else 'none'}",
    ]
    if task.action is None:
        lines.append("- action: none")
    else:
        expected_effect = task.action.expected_effect
        lines.extend(
            [
                "- action:",
                f"  - action_type: {task.action.action_type}",
                f"  - target_hint: {task.action.target_hint}",
                f"  - expected_effect: {expected_effect.type}",
                f"  - expected_value: {expected_effect.value or 'none'}",
            ]
        )
    return "\n".join(lines)


def _skill_instruction_section(skill: SkillPromptContext | None) -> str:
    lines = ["# Skill Instruction", ""]
    if skill is None:
        lines.append("No skill selected; execute as a general browser task.")
        return "\n".join(lines)

    lines.extend(
        [
            f"- skill_id: {skill.skill_id}",
            f"- name: {skill.name}",
            f"- version: {skill.version}",
            f"- description: {skill.description}",
            "",
            skill.instruction.strip(),
        ]
    )
    if skill.plan is not None:
        lines.extend(["", "## Skill Plan", ""])
        objective = skill.plan.get("objective")
        if objective:
            lines.append(f"- objective: {objective}")
        steps = skill.plan.get("steps")
        if isinstance(steps, list) and steps:
            lines.append("- steps:")
            for step in steps:
                lines.append(f"  - {step}")
        required_evidence = skill.plan.get("required_evidence")
        if isinstance(required_evidence, list) and required_evidence:
            lines.append("- required_evidence:")
            for item in required_evidence:
                lines.append(f"  - {item}")
    return "\n".join(lines)


def _safety_section(context: WebAgentContextSnapshot) -> str:
    safety = context.safety
    lines = [
        "# Safety Policy",
        "",
        f"- mode: {safety.mode}",
        f"- allow_login: {safety.allow_login}",
        f"- allow_captcha_bypass: {safety.allow_captcha_bypass}",
        f"- allow_sensitive_input: {safety.allow_sensitive_input}",
        f"- allow_external_submit: {safety.allow_external_submit}",
    ]
    return "\n".join(lines)


def _runtime_version_section(context: WebAgentContextSnapshot) -> str:
    version = context.version
    lines = [
        "# Runtime Version",
        "",
        f"- runtime_version: {version.runtime_version}",
        f"- skill_version: {version.skill_version}",
        f"- prompt_version: {version.prompt_version}",
        f"- tool_schema_version: {version.tool_schema_version}",
        f"- review_policy_version: {version.review_policy_version}",
        f"- eval_case_version: {version.eval_case_version or 'none'}",
        f"- model: {version.model}",
    ]
    return "\n".join(lines)


def _core_tools_section(tools: list[ToolSpec]) -> str:
    lines = ["# Core Tools", ""]
    for tool in tools:
        lines.extend(
            [
                f"## {tool.tool_id}",
                f"- name: {tool.name}",
                f"- description: {tool.description}",
                f"- permission: {tool.permission}",
                f"- risk_level: {tool.risk_level}",
                f"- prompt: {tool.prompt}",
                "",
            ]
        )
    return "\n".join(lines).rstrip()


def _lazy_tools_section(tools: list[ToolSpec]) -> str:
    lines = [
        "# Lazy Tools",
        "",
        "If a lazy tool is needed, request ToolSearch before using it.",
        "",
    ]
    for tool in tools:
        lines.append(f"- {tool.tool_id}: {tool.name} - {tool.description}")
    return "\n".join(lines)


def _agents_md_section(instructions: list[AgentsMdInstruction]) -> str:
    lines = ["# Agents.md Instructions", ""]
    if not instructions:
        lines.append("No AGENTS.md instructions loaded.")
        return "\n".join(lines)

    for instruction in instructions:
        lines.extend(
            [
                f"## {instruction.source_path}",
                instruction.content.strip(),
                "",
            ]
        )
    return "\n".join(lines).rstrip()


def _runtime_reminders_section(reminders: list[RuntimeReminder]) -> str:
    lines = ["# Runtime Reminders", ""]
    if not reminders:
        lines.append("No runtime reminders.")
        return "\n".join(lines)

    for reminder in reminders:
        lines.extend(
            [
                (
                    f'<system-reminder level="{_xml_escape(reminder.level)}" '
                    f'source="{_xml_escape(reminder.source)}">'
                ),
                _xml_escape(reminder.message),
                "</system-reminder>",
            ]
        )
    return "\n".join(lines)


def _compacted_context_section(context_pack: ContextPack) -> str:
    lines = [
        "# Compacted Runtime Context",
        "",
        f"- task_goal: {context_pack.task_goal or 'none'}",
    ]
    state = context_pack.current_state
    lines.append("- current_browser_state:")
    if state is None:
        lines.append("  - unavailable")
    else:
        lines.extend(
            [
                f"  - current_url: {state.current_url or 'none'}",
                f"  - current_title: {state.current_title or 'none'}",
                f"  - visible_text_preview: {state.visible_text_preview or 'none'}",
                f"  - screenshot_path: {state.screenshot_path or 'none'}",
            ]
        )

    lines.append("- key_previous_steps:")
    if not context_pack.key_steps:
        lines.append("  - none")
    for step in context_pack.key_steps[:8]:
        lines.append(
            f"  - {step.step_id}: [{step.kind}] {step.status or 'unknown'} "
            f"{step.summary}"
        )

    lines.append("- recent_steps:")
    if not context_pack.recent_steps:
        lines.append("  - none")
    for step in context_pack.recent_steps[:8]:
        lines.append(
            f"  - {step.step_id}: [{step.kind}] {step.status or 'unknown'} "
            f"{step.summary}"
        )

    lines.append("- evidence_refs:")
    if not context_pack.evidence_refs:
        lines.append("  - none")
    for ref in context_pack.evidence_refs[:12]:
        lines.append(
            f"  - {ref.evidence_id}: {ref.kind}; {ref.source_url or 'no-url'}; "
            f"{ref.text_preview or ''}"
        )

    recovery = context_pack.recovery_state
    lines.append("- recovery_state:")
    if recovery is None:
        lines.append("  - none")
    else:
        lines.extend(
            [
                f"  - total_attempts: {recovery.total_attempts}",
                f"  - recovered_count: {recovery.recovered_count}",
                f"  - failed_count: {recovery.failed_count}",
                f"  - blocked_count: {recovery.blocked_count}",
            ]
        )

    risk = context_pack.risk_state
    lines.append("- risk_approval_state:")
    if risk is None:
        lines.append("  - none")
    else:
        lines.extend(
            [
                f"  - has_pending_approval: {risk.has_pending_approval}",
                f"  - pending_approval_ids: {', '.join(risk.pending_approval_ids) or 'none'}",
                f"  - blocked: {risk.blocked}",
                f"  - risk_signal_count: {len(risk.risk_signals)}",
            ]
        )

    if context_pack.next_action_hint:
        lines.extend(["- next_action_hint:", f"  - {context_pack.next_action_hint}"])
    return "\n".join(lines)


def _output_rules_section() -> str:
    return "\n".join(
        [
            "# Output Rules",
            "",
            "- Do not claim unsupported facts.",
            "- Preserve source URL when extracting evidence.",
            "- Do not bypass login, captcha, paywall or access control.",
            "- Do not enter real password, payment or personal identity data.",
        ]
    )


def _xml_escape(value: str) -> str:
    return value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
