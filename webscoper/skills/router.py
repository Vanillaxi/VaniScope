from __future__ import annotations

from dataclasses import dataclass

from webscoper.schemas.task import TaskSpec
from webscoper.skills.base import Skill
from webscoper.skills.registry import SkillRegistry, create_default_skill_registry


@dataclass(frozen=True)
class SkillRoute:
    skill: Skill | None
    task: TaskSpec
    reason: str


class SkillRouter:
    def __init__(self, registry: SkillRegistry | None = None) -> None:
        self.registry = registry or create_default_skill_registry()

    def route(self, task: TaskSpec) -> SkillRoute:
        if task.skill_id:
            skill = self.registry.get(task.skill_id)
            routed_task = task.model_copy(
                update={
                    "skill_id": skill.definition.skill_id,
                    "task_type": _preferred_task_type(task, skill),
                }
            )
            return SkillRoute(skill=skill, task=routed_task, reason="explicit_skill_id")

        if task.task_type and task.task_type != "browser_task":
            matches = self.registry.find_by_task_type(task.task_type)
            if matches:
                skill = matches[0]
                routed_task = task.model_copy(update={"skill_id": skill.definition.skill_id})
                return SkillRoute(skill=skill, task=routed_task, reason="task_type")

        if task.target_url and (task.query or task.research_goal):
            skill = self.registry.get("docs_research")
            routed_task = task.model_copy(
                update={"skill_id": "docs_research", "task_type": "docs_research"}
            )
            return SkillRoute(skill=skill, task=routed_task, reason="url_with_query")

        return SkillRoute(skill=None, task=task, reason="browser_task_default")


def _preferred_task_type(task: TaskSpec, skill: Skill) -> str:
    if task.task_type != "browser_task":
        return task.task_type
    if skill.definition.supported_task_types:
        return skill.definition.supported_task_types[0]
    return task.task_type
