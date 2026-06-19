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

    def find_by_task_type(self, task_type: str) -> list[Skill]:
        return [
            skill
            for skill in self._skills.values()
            if task_type in skill.definition.supported_task_types
        ]


def create_default_skill_registry() -> SkillRegistry:
    registry = SkillRegistry()
    registry.register(DocsResearchSkill())
    registry.register(GitHubIssueResearchSkill())
    return registry
