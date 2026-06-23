from __future__ import annotations

from webscoper.skills.base import Skill
from webscoper.skills.docs_research import DocsResearchSkill
from webscoper.skills.github_issue_research import GitHubIssueResearchSkill


class SkillRegistry:
    def __init__(self, skills: list[Skill] | None = None) -> None:
        self._skills: dict[str, Skill] = {}
        for skill in skills or []:
            self.register(skill)

    def register(self, skill: Skill) -> None:
        skill_id = skill.definition.skill_id
        if skill_id in self._skills:
            raise ValueError(f"Skill already registered: {skill_id}")
        self._skills[skill_id] = skill

    def get(self, skill_id: str) -> Skill:
        try:
            return self._skills[skill_id]
        except KeyError as exc:
            raise KeyError(f"Unknown skill: {skill_id}") from exc

    def list_skills(self) -> list[Skill]:
        return list(self._skills.values())

    def list_descriptors(self) -> list[dict[str, object]]:
        descriptors: list[dict[str, object]] = []
        for skill in self._skills.values():
            definition = skill.definition
            descriptors.append(
                {
                    "id": definition.skill_id,
                    "description": definition.description,
                    "triggers": definition.triggers,
                    "supported_url_patterns": definition.supported_url_patterns,
                    "required_tools": definition.required_tools,
                    "optional_tools": definition.optional_tools,
                    "default_report_shape": definition.default_report_shape,
                    "budget_hint": definition.budget_hint,
                    "enabled": definition.enabled,
                }
            )
        return descriptors

    def find_by_task_type(self, task_type: str) -> list[Skill]:
        return [
            skill
            for skill in self._skills.values()
            if skill.definition.enabled
            and task_type in skill.definition.supported_task_types
        ]


def create_default_skill_registry() -> SkillRegistry:
    registry = SkillRegistry()
    registry.register(DocsResearchSkill())
    registry.register(GitHubIssueResearchSkill())
    return registry
