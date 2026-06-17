from __future__ import annotations

from webscoper.schemas.context import WebAgentContextSnapshot
from webscoper.schemas.prompt import (
    AgentsMdInstruction,
    PromptBuildResult,
    RuntimeReminder,
)
from webscoper.schemas.tool import ToolSpec
from webscoper.tools.registry import ToolRegistry


class DynamicPromptBuilder:
    def __init__(self, tool_registry: ToolRegistry) -> None:
        self.tool_registry = tool_registry

    def build(
        self,
        context: WebAgentContextSnapshot,
        agents_md_instructions: list[AgentsMdInstruction] | None = None,
        runtime_reminders: list[RuntimeReminder] | None = None,
    ) -> PromptBuildResult:
        agents_md_instructions = agents_md_instructions or []
        runtime_reminders = runtime_reminders or []
        catalog = self.tool_registry.snapshot()

        sections = {
            "identity": _identity_section(),
            "task": _task_section(context),
            "safety": _safety_section(context),
            "permission_mode": context.safety.mode,
            "runtime_version": _runtime_version_section(context),
            "core_tools": _core_tools_section(catalog.core_tools),
            "lazy_tools": _lazy_tools_section(catalog.lazy_tools),
            "agents_md": _agents_md_section(agents_md_instructions),
            "runtime_reminders": _runtime_reminders_section(runtime_reminders),
            "output_rules": _output_rules_section(),
        }
        ordered_keys = [
            "identity",
            "task",
            "safety",
            "permission_mode",
            "runtime_version",
            "core_tools",
            "lazy_tools",
            "agents_md",
            "runtime_reminders",
            "output_rules",
        ]
        prompt_text = "\n\n".join(sections[key] for key in ordered_keys)

        return PromptBuildResult(
            prompt_text=prompt_text,
            sections=sections,
            loaded_agents_md_paths=[
                instruction.source_path for instruction in agents_md_instructions
            ],
            core_tool_ids=[tool.tool_id for tool in catalog.core_tools],
            lazy_tool_ids=[tool.tool_id for tool in catalog.lazy_tools],
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
        f"- target_url: {task.target_url}",
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
