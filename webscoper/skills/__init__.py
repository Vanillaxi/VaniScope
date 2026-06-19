from webscoper.skills.base import (
    SkillDefinition,
    SkillInput,
    SkillInstruction,
    SkillPlan,
    SkillResult,
)
from webscoper.skills.docs_research import DocsResearchSkill
from webscoper.skills.github_issue_research import GitHubIssueResearchSkill
from webscoper.skills.registry import SkillRegistry, create_default_skill_registry
from webscoper.skills.router import SkillRoute, SkillRouter

__all__ = [
    "DocsResearchSkill",
    "GitHubIssueResearchSkill",
    "SkillDefinition",
    "SkillInput",
    "SkillInstruction",
    "SkillPlan",
    "SkillRegistry",
    "SkillResult",
    "SkillRoute",
    "SkillRouter",
    "create_default_skill_registry",
]
