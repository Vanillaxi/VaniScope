from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, Field

from webscoper.schemas.artifact import EvidenceItem
from webscoper.schemas.browser import PageObservation
from webscoper.schemas.task import TaskSpec
from webscoper.skills.base import (
    SkillDefinition,
    SkillInput,
    SkillInstruction,
    SkillPlan,
    SkillResult,
)


Difficulty = Literal["low", "medium", "high"]
ContributionValue = Literal["low", "medium", "high"]


GITHUB_ISSUE_RESEARCH_INSTRUCTION = """Treat the opened issue or PR page as the source of truth.
Do not invent repository facts that are not present in the page.
Always cite evidence for difficulty, contribution value, risks, and recommendation.
Separate page facts from your judgment.
Mention uncertainty when evidence is insufficient.
Never access private repositories or perform write actions.
Never submit comments, create pull requests, or modify GitHub state.

中文要求：明确区分“页面事实”和“你的判断”。难度、含金量、风险都必须有 evidence 支撑。信息不足时直接说明不足。"""


class GitHubIssueSkillResult(SkillResult):
    task_type: str = "github_issue_research"
    recommendation: str
    difficulty: Difficulty
    contribution_value: ContributionValue
    affected_modules: list[str] = Field(default_factory=list)


@dataclass(frozen=True)
class GitHubIssueResearchSkill:
    definition: SkillDefinition = field(
        default_factory=lambda: SkillDefinition(
            skill_id="github_issue_research",
            name="GitHub Issue Research",
            description=(
                "Analyze a GitHub issue or PR task and produce an "
                "evidence-backed contribution report."
            ),
            version="0.1.0",
            triggers=[
                "github issue",
                "github pr",
                "repository issue",
                "pull request",
                "contribution",
            ],
            supported_url_patterns=["github.com/*/*/issues/*", "github.com/*/*/pull/*"],
            supported_task_types=[
                "github_issue_research",
                "issue_research",
                "contribution_research",
            ],
            required_tools=[
                "browser_open",
                "browser_observe",
                "browser_extract",
                "github_fetch_issue",
            ],
            optional_tools=["github_fetch_pr", "browser_screenshot"],
            default_report_shape={
                "sections": [
                    "Task",
                    "Page Facts",
                    "Engineering Judgment",
                    "Affected Modules",
                    "Difficulty Estimate",
                    "Risks",
                    "Evidence",
                ]
            },
            budget_hint="one public/local GitHub issue or PR page",
            risk_level="read_only",
            instruction=SkillInstruction(
                title="GitHub Issue Research Instructions",
                content=GITHUB_ISSUE_RESEARCH_INSTRUCTION,
            ),
        ),
    )

    def build_input(self, task: TaskSpec) -> SkillInput:
        return SkillInput(
            raw_task=task.raw_input,
            url=task.target_url,
            query=task.query or task.research_goal,
            expected_output=task.expected_output,
            constraints=task.constraints,
            language=task.language,
        )

    def plan(self, skill_input: SkillInput) -> SkillPlan:
        query = skill_input.query or skill_input.raw_task
        return SkillPlan(
            skill_id=self.definition.skill_id,
            objective=f"Analyze the issue or PR contribution task with page evidence: {query}",
            steps=[
                "Open the local issue page through the Browser ToolGateway.",
                "Observe and extract issue metadata, labels, discussion, affected modules, and acceptance criteria.",
                "Assess difficulty, contribution value, risks, and recommendation from captured evidence.",
                "Write a structured contribution report with evidence references.",
                "Review that the report answers the query and cites evidence.",
            ],
            required_evidence=[
                "issue title",
                "labels",
                "affected modules",
                "maintainer requirement",
                "acceptance criteria",
                "suggested implementation",
            ],
            expected_artifacts=[
                "final_report.md",
                "evidence.jsonl",
                "review.json",
                "skill_result.json",
                "tool_audit.jsonl",
            ],
        )

    def annotate_evidence(self, evidence_items: list[EvidenceItem]) -> None:
        for item in evidence_items:
            item.metadata.setdefault("skill_id", self.definition.skill_id)
            item.metadata.setdefault("section", "github_issue_page")
            item.metadata.setdefault(
                "covered_sections",
                _covered_sections(item.text or ""),
            )

    def build_report(
        self,
        task: TaskSpec,
        evidence_items: list[EvidenceItem],
        final_observation: PageObservation | None = None,
    ) -> str:
        analysis = analyze_issue(task, evidence_items, final_observation)
        if _is_zh(task.language):
            return _zh_report(task, analysis)
        return _en_report(task, analysis)

    def build_result(
        self,
        task: TaskSpec,
        evidence_items: list[EvidenceItem],
        artifact_names: list[str],
        final_observation: PageObservation | None = None,
    ) -> GitHubIssueSkillResult:
        analysis = analyze_issue(task, evidence_items, final_observation)
        return GitHubIssueSkillResult(
            skill_id=self.definition.skill_id,
            task_type="github_issue_research",
            status="success" if analysis.evidence_ids else "insufficient_info",
            summary=analysis.summary,
            recommendation=analysis.recommendation,
            difficulty=analysis.difficulty,
            contribution_value=analysis.contribution_value,
            affected_modules=analysis.affected_modules,
            evidence_ids=analysis.evidence_ids,
            artifact_names=artifact_names,
            metadata={
                "query": task.query or task.research_goal or task.raw_input,
                "language": task.language,
                "repository": analysis.repository,
                "issue_number": analysis.issue_number,
                "labels": analysis.labels,
                "risk_count": len(analysis.risks),
                "source_url": analysis.source_url,
            },
        )


class IssueAnalysis(BaseModel):
    source_url: str
    page_title: str
    query: str
    repository: str = "unknown"
    issue_title: str = "unknown"
    issue_number: str = "unknown"
    labels: list[str] = Field(default_factory=list)
    affected_modules: list[str] = Field(default_factory=list)
    needs_changes: list[str] = Field(default_factory=list)
    acceptance_criteria: list[str] = Field(default_factory=list)
    maintainer_requirements: list[str] = Field(default_factory=list)
    suggested_plan: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    difficulty: Difficulty = "medium"
    contribution_value: ContributionValue = "medium"
    recommendation: str = "worth_doing"
    summary: str
    evidence_ids: list[str] = Field(default_factory=list)


def analyze_issue(
    task: TaskSpec,
    evidence_items: list[EvidenceItem],
    observation: PageObservation | None,
) -> IssueAnalysis:
    text = _combined_text(evidence_items)
    source_url = _source_url(task, evidence_items, observation)
    page_title = _page_title(evidence_items, observation)
    repository = _field(text, "Repository") or _field(text, "Project") or "unknown"
    issue_title = _field(text, "Issue") or _field(text, "Title") or page_title
    issue_number = _field(text, "Issue Number") or _issue_number(text)
    labels = _section_items(text, "Labels") or _known_labels(text)
    affected_modules = _section_items(text, "Affected Modules") or _section_items(
        text,
        "Affected Files",
    )
    needs_changes = _section_items(text, "Suggested Implementation")
    acceptance_criteria = _section_items(text, "Acceptance Criteria")
    maintainer_requirements = _section_items(text, "Maintainer Comments")
    risks = _section_items(text, "Risks") or _infer_risks(text, acceptance_criteria)
    difficulty = _difficulty(text, affected_modules, acceptance_criteria, risks)
    contribution_value = _contribution_value(labels, text)
    recommendation = _recommendation(difficulty, contribution_value, risks)
    suggested_plan = needs_changes or _suggested_plan(affected_modules)
    evidence_ids = [item.evidence_id for item in evidence_items[:5]]
    query = task.query or task.research_goal or task.raw_input
    summary = (
        f"{repository} {issue_number}: {issue_title}. "
        f"Recommendation: {recommendation}; difficulty: {difficulty}; "
        f"contribution value: {contribution_value}."
    )
    return IssueAnalysis(
        source_url=source_url,
        page_title=page_title,
        query=query,
        repository=repository,
        issue_title=issue_title,
        issue_number=issue_number,
        labels=labels,
        affected_modules=affected_modules,
        needs_changes=needs_changes,
        acceptance_criteria=acceptance_criteria,
        maintainer_requirements=maintainer_requirements,
        suggested_plan=suggested_plan,
        risks=risks,
        difficulty=difficulty,
        contribution_value=contribution_value,
        recommendation=recommendation,
        summary=summary,
        evidence_ids=evidence_ids,
    )


def _en_report(task: TaskSpec, analysis: IssueAnalysis) -> str:
    refs = _refs(analysis.evidence_ids)
    return "\n".join(
        [
            "# GitHub Issue Research Report",
            "",
            "## Task",
            "",
            f"- task_id: {task.task_id}",
            "- skill_id: github_issue_research",
            f"- query: {analysis.query}",
            "",
            "## Source URL",
            "",
            f"- {analysis.source_url}",
            f"- page_title: {analysis.page_title}",
            "",
            "## Result",
            "",
            (
                f"- Recommendation: {analysis.recommendation}; difficulty: "
                f"{analysis.difficulty}; contribution value: "
                f"{analysis.contribution_value}. {refs}"
            ),
            "",
            "## Issue Summary",
            "",
            f"- {analysis.summary} {refs}",
            "",
            "## Repository / Issue Metadata",
            "",
            f"- Repository: {analysis.repository} {refs}",
            f"- Issue: {analysis.issue_title}",
            f"- Issue number: {analysis.issue_number}",
            f"- Labels: {', '.join(analysis.labels) or 'unknown'}",
            "",
            "## What Needs To Be Changed",
            "",
            *_bullet_lines(analysis.needs_changes, refs),
            "",
            "## Affected Modules",
            "",
            *_bullet_lines(analysis.affected_modules, refs),
            "",
            "## Difficulty Estimate",
            "",
            f"- {analysis.difficulty}: based on affected modules, benchmark requirements, and clone-semantics caveats. {refs}",
            "",
            "## Contribution Value",
            "",
            f"- {analysis.contribution_value}: based on labels and performance impact described on the page. {refs}",
            "",
            "## Risks / Caveats",
            "",
            *_bullet_lines(analysis.risks, refs),
            "",
            "## Suggested Implementation Plan",
            "",
            *_bullet_lines(analysis.suggested_plan, refs),
            "",
            "## Evidence",
            "",
            *_evidence_lines(analysis),
            "",
            "## Final Recommendation",
            "",
            f"- {analysis.recommendation}. Proceed if the contributor can add benchmarks and preserve clone semantics. {refs}",
            "",
        ]
    )


def _zh_report(task: TaskSpec, analysis: IssueAnalysis) -> str:
    refs = _refs(analysis.evidence_ids)
    return "\n".join(
        [
            "# GitHub Issue Research Report",
            "",
            "## Task",
            "",
            f"- task_id: {task.task_id}",
            "- skill_id: github_issue_research",
            f"- query: {analysis.query}",
            "",
            "## Source URL",
            "",
            f"- {analysis.source_url}",
            f"- page_title: {analysis.page_title}",
            "",
            "## Result",
            "",
            f"- 建议：{analysis.recommendation}；难度：{analysis.difficulty}；贡献价值：{analysis.contribution_value}。{refs}",
            "",
            "## Issue Summary",
            "",
            f"- {analysis.summary} {refs}",
            "",
            "## Repository / Issue Metadata",
            "",
            f"- Repository: {analysis.repository} {refs}",
            f"- Issue: {analysis.issue_title}",
            f"- Issue number: {analysis.issue_number}",
            f"- Labels: {', '.join(analysis.labels) or 'unknown'}",
            "",
            "## What needs to be changed",
            "",
            *_bullet_lines(analysis.needs_changes, refs),
            "",
            "## Affected Modules",
            "",
            *_bullet_lines(analysis.affected_modules, refs),
            "",
            "## Difficulty Estimate",
            "",
            f"- {analysis.difficulty}：依据受影响模块、benchmark 要求和 clone semantics 风险判断。{refs}",
            "",
            "## Contribution Value",
            "",
            f"- {analysis.contribution_value}：依据页面标签和性能收益描述判断。{refs}",
            "",
            "## Risks / Caveats",
            "",
            *_bullet_lines(analysis.risks, refs),
            "",
            "## Suggested Implementation Plan",
            "",
            *_bullet_lines(analysis.suggested_plan, refs),
            "",
            "## Evidence",
            "",
            *_evidence_lines(analysis),
            "",
            "## Final Recommendation",
            "",
            f"- {analysis.recommendation}。如果贡献者能补 benchmark 并保持 clone semantics，值得做。{refs}",
            "",
        ]
    )


def _combined_text(evidence_items: list[EvidenceItem]) -> str:
    return "\n".join(item.text or "" for item in evidence_items)


def _source_url(
    task: TaskSpec,
    evidence_items: list[EvidenceItem],
    observation: PageObservation | None,
) -> str:
    if observation is not None and observation.url:
        return observation.url
    for item in evidence_items:
        if item.source_url:
            return item.source_url
    return task.target_url


def _page_title(
    evidence_items: list[EvidenceItem],
    observation: PageObservation | None,
) -> str:
    if observation is not None and observation.title:
        return observation.title
    for item in evidence_items:
        if item.page_title:
            return item.page_title
    return "unknown"


def _field(text: str, label: str) -> str | None:
    match = re.search(rf"(?im)^\s*{re.escape(label)}\s*:\s*(.+)$", text)
    return match.group(1).strip() if match else None


def _issue_number(text: str) -> str:
    match = re.search(r"#\d+", text)
    return match.group(0) if match else "unknown"


def _section_items(text: str, heading: str) -> list[str]:
    section = _section(text, heading)
    if not section:
        return []
    items: list[str] = []
    for line in section.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith(("- ", "* ")):
            items.append(stripped[2:].strip())
        elif re.match(r"^\d+\.\s+", stripped):
            items.append(re.sub(r"^\d+\.\s+", "", stripped).strip())
        elif len(stripped) < 180:
            items.append(stripped)
    return _dedupe(items)


def _known_labels(text: str) -> list[str]:
    known = [
        "good first issue",
        "performance",
        "protocol",
        "common",
        "bug",
        "documentation",
        "high risk",
    ]
    lowered = text.lower()
    return [label for label in known if label in lowered]


def _section(text: str, heading: str) -> str:
    pattern = rf"(?ims)^\s*{re.escape(heading)}\s*$\n(?P<body>.*?)(?=^\s*[A-Z][A-Za-z /]+(?:\s*)$|\Z)"
    match = re.search(pattern, text)
    return match.group("body").strip() if match else ""


def _covered_sections(text: str) -> list[str]:
    names = [
        "Repository",
        "Issue",
        "Labels",
        "Affected Modules",
        "Maintainer Comments",
        "Acceptance Criteria",
        "Suggested Implementation",
    ]
    return [name for name in names if name.lower() in text.lower()]


def _difficulty(
    text: str,
    affected_modules: list[str],
    acceptance_criteria: list[str],
    risks: list[str],
) -> Difficulty:
    lowered = text.lower()
    if "high risk" in lowered or len(risks) >= 4:
        return "high"
    if "benchmark" in lowered or "clone semantics" in lowered or len(affected_modules) >= 2:
        return "medium"
    if len(acceptance_criteria) <= 2 and len(affected_modules) <= 1:
        return "low"
    return "medium"


def _contribution_value(labels: list[str], text: str) -> ContributionValue:
    lowered = " ".join(labels).lower() + " " + text.lower()
    if "performance" in lowered or "protocol" in lowered:
        return "high"
    if "good first issue" in lowered or "common" in lowered:
        return "medium"
    return "low"


def _recommendation(
    difficulty: Difficulty,
    contribution_value: ContributionValue,
    risks: list[str],
) -> str:
    if difficulty == "high" and contribution_value != "high":
        return "defer"
    if difficulty == "high":
        return "worth_doing_with_caution"
    if contribution_value == "high":
        return "worth_doing"
    if risks:
        return "worth_doing_with_caution"
    return "worth_doing"


def _infer_risks(text: str, acceptance_criteria: list[str]) -> list[str]:
    risks: list[str] = []
    lowered = text.lower()
    if "clone semantics" in lowered:
        risks.append("Must preserve clone semantics.")
    if "benchmark" in lowered:
        risks.append("Benchmark coverage is required.")
    if not acceptance_criteria:
        risks.append("Acceptance criteria are missing or incomplete.")
    return risks


def _suggested_plan(affected_modules: list[str]) -> list[str]:
    if not affected_modules:
        return ["Confirm affected modules from issue discussion before implementation."]
    return [
        f"Inspect {module} and identify unnecessary parameter-copying paths."
        for module in affected_modules
    ] + ["Add regression tests and benchmark coverage before proposing a patch."]


def _bullet_lines(items: list[str], refs: str) -> list[str]:
    if not items:
        return [f"- Not enough page evidence to determine this. {refs}"]
    return [f"- {item} {refs}" for item in items]


def _evidence_lines(analysis: IssueAnalysis) -> list[str]:
    fields = [
        f"Issue title: {analysis.issue_title}",
        f"Labels: {', '.join(analysis.labels) or 'unknown'}",
        f"Affected modules: {', '.join(analysis.affected_modules) or 'unknown'}",
        f"Maintainer requirements: {'; '.join(analysis.maintainer_requirements) or 'unknown'}",
        f"Acceptance criteria: {'; '.join(analysis.acceptance_criteria) or 'unknown'}",
        f"Suggested implementation: {'; '.join(analysis.suggested_plan) or 'unknown'}",
    ]
    evidence_id = analysis.evidence_ids[0] if analysis.evidence_ids else "no_evidence"
    return [f"- [{evidence_id}] {field}" for field in fields]


def _refs(evidence_ids: list[str]) -> str:
    if not evidence_ids:
        return "[no evidence]"
    return "Evidence: " + ", ".join(f"[{item}]" for item in evidence_ids[:3])


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        output.append(value)
    return output


def _is_zh(language: str) -> bool:
    return language.lower().startswith("zh")
