from __future__ import annotations

import re
from dataclasses import dataclass, field

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


DOCS_RESEARCH_INSTRUCTION = """Use the opened documentation page as the primary source.
Prefer page content over assumptions. Do not invent details that are not present on the page.
Every conclusion in the final report must be tied to captured evidence ids.
The final report must include the source URL.
If the page does not contain enough information to answer the query, say what is missing."""


@dataclass(frozen=True)
class DocsResearchSkill:
    definition: SkillDefinition = field(
        default_factory=lambda: SkillDefinition(
            skill_id="docs_research",
            name="Docs Research",
            description="Read one documentation page and produce an evidence-backed report.",
            version="0.1.0",
            triggers=["docs", "documentation", "API reference", "guide"],
            supported_url_patterns=["/docs", "docs.", "readthedocs", "developer."],
            supported_task_types=["docs_research"],
            required_tools=[
                "browser_open",
                "browser_observe",
                "browser_extract",
                "browser_screenshot",
                "finish_task",
            ],
            optional_tools=["docs_extract", "table_extract"],
            default_report_shape={
                "sections": ["Task", "Source URL", "Summary", "Key Findings", "Evidence", "Limitations"]
            },
            budget_hint="one public/local documentation page",
            risk_level="safe",
            instruction=SkillInstruction(
                title="Docs Research Instructions",
                content=DOCS_RESEARCH_INSTRUCTION,
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
            objective=f"Answer the documentation question with page evidence: {query}",
            steps=[
                "Open the documentation page through the Browser ToolGateway.",
                "Observe and extract visible documentation text.",
                "Select evidence relevant to the query.",
                "Write a structured report with evidence references.",
                "Review the report for answer coverage and unsupported claims.",
            ],
            required_evidence=[
                "page title",
                "source URL",
                "visible text spans relevant to the query",
            ],
            expected_artifacts=[
                "final_report.md",
                "evidence.jsonl",
                "review.json",
                "skill_result.json",
                "tool_audit.jsonl",
            ],
        )

    def build_report(
        self,
        task: TaskSpec,
        evidence_items: list[EvidenceItem],
        final_observation: PageObservation | None = None,
    ) -> str:
        source_url = _source_url(task, evidence_items, final_observation)
        title = _page_title(evidence_items, final_observation)
        query = task.query or task.research_goal or task.raw_input
        relevant_items = _relevant_items(query, evidence_items)

        findings = _findings(query, relevant_items, task.language)
        limitations = _limitations(query, relevant_items, task.language)
        summary = _summary(query, relevant_items, task.language)

        lines = [
            "# Docs Research Report",
            "",
            "## Task",
            "",
            f"- task_id: {task.task_id}",
            f"- skill_id: {self.definition.skill_id}",
            f"- query: {query}",
            f"- expected_output: {task.expected_output or 'none'}",
            "",
            "## Source URL",
            "",
            f"- {source_url or task.target_url}",
            f"- page_title: {title or 'unknown'}",
            "",
            "## Summary",
            "",
            summary,
            "",
            "## Result",
            "",
            summary,
            "",
            "## Key Findings",
            "",
        ]
        lines.extend(findings or ["- No directly relevant finding was found in evidence."])
        lines.extend(["", "## Evidence", ""])
        if relevant_items:
            for item in relevant_items:
                text = _compact_text(item.text)
                lines.append(
                    f"- [{item.evidence_id}] {item.page_title or 'Page'} "
                    f"from {item.source_url or source_url or 'unknown source'}: {text}"
                )
        else:
            lines.append("- No evidence was captured.")
        lines.extend(["", "## Limitations", ""])
        lines.extend(limitations)
        lines.append("")
        return "\n".join(lines)

    def build_result(
        self,
        task: TaskSpec,
        evidence_items: list[EvidenceItem],
        artifact_names: list[str],
    ) -> SkillResult:
        query = task.query or task.research_goal or task.raw_input
        relevant_items = _relevant_items(query, evidence_items)
        status = "success" if relevant_items else "insufficient_info"
        summary = (
            f"Docs research completed for query: {query}"
            if relevant_items
            else f"Docs research could not find direct page evidence for query: {query}"
        )
        return SkillResult(
            skill_id=self.definition.skill_id,
            status=status,
            summary=summary,
            evidence_ids=[item.evidence_id for item in relevant_items],
            artifact_names=artifact_names,
            metadata={
                "query": query,
                "language": task.language,
                "evidence_count": len(evidence_items),
                "relevant_evidence_count": len(relevant_items),
            },
        )


def _source_url(
    task: TaskSpec,
    evidence_items: list[EvidenceItem],
    observation: PageObservation | None,
) -> str | None:
    if observation is not None and observation.url:
        return observation.url
    for item in evidence_items:
        if item.source_url:
            return item.source_url
    return task.target_url


def _page_title(
    evidence_items: list[EvidenceItem],
    observation: PageObservation | None,
) -> str | None:
    if observation is not None and observation.title:
        return observation.title
    for item in evidence_items:
        if item.page_title:
            return item.page_title
    return None


def _relevant_items(query: str, evidence_items: list[EvidenceItem]) -> list[EvidenceItem]:
    terms = _query_terms(query)
    if not terms:
        return evidence_items[:3]
    matched = [
        item
        for item in evidence_items
        if _score_text(terms, f"{item.page_title or ''} {item.text or ''}") > 0
    ]
    return matched[:5]


def _findings(
    query: str,
    evidence_items: list[EvidenceItem],
    language: str,
) -> list[str]:
    lines: list[str] = []
    for item in evidence_items[:5]:
        snippets = _matched_sentences(query, item.text or "")
        if not snippets and item.text:
            snippets = [_compact_text(item.text, limit=180)]
        for snippet in snippets[:6]:
            if _is_zh(language):
                lines.append(f"- {snippet} [{item.evidence_id}]")
            else:
                lines.append(f"- {snippet} [{item.evidence_id}]")
    return lines


def _summary(query: str, evidence_items: list[EvidenceItem], language: str) -> str:
    if evidence_items:
        refs = ", ".join(f"[{item.evidence_id}]" for item in evidence_items[:3])
        if _is_zh(language):
            return f"该文档页面包含与问题“{query}”相关的信息，主要证据为 {refs}。"
        return f"The documentation page contains information relevant to {query!r}. Primary evidence: {refs}."
    if _is_zh(language):
        return f"没有在页面证据中找到足够信息回答“{query}”。"
    return f"The captured page evidence is not sufficient to answer {query!r}."


def _limitations(
    query: str,
    evidence_items: list[EvidenceItem],
    language: str,
) -> list[str]:
    if evidence_items:
        if _is_zh(language):
            return ["- 结论只基于当前打开页面的可见文本；未访问外部网页或真实网络。"]
        return ["- Conclusions are limited to visible text captured from the opened page; no external website was accessed."]
    if _is_zh(language):
        return [f"- 页面证据不足，无法确认与“{query}”相关的结论。"]
    return [f"- Page evidence was insufficient to confirm claims related to {query!r}."]


def _matched_sentences(query: str, text: str) -> list[str]:
    terms = _query_terms(query)
    line_matches = _matched_lines_with_context(terms, text)
    if line_matches:
        return line_matches[:6]
    sentences = [
        part.strip()
        for part in re.split(r"(?<=[.!?。！？])\s+|\n+", text)
        if part.strip()
    ]
    matched = [
        _compact_text(sentence, limit=220)
        for sentence in sentences
        if _score_text(terms, sentence) > 0
    ]
    return matched[:4]


def _matched_lines_with_context(terms: set[str], text: str) -> list[str]:
    lines = [" ".join(line.split()) for line in text.splitlines()]
    lines = [line for line in lines if line]
    matched: list[tuple[int, str]] = []
    for index, line in enumerate(lines):
        score = _score_text(terms, line)
        if score <= 0:
            continue
        snippet = line
        if index + 1 < len(lines) and _is_useful_context_line(lines[index + 1]):
            snippet = f"{snippet} {lines[index + 1]}"
            score += 2
        matched.append((score, _compact_text(snippet, limit=240)))
    matched.sort(key=lambda item: item[0], reverse=True)
    return _dedupe([snippet for _score, snippet in matched])


def _is_useful_context_line(line: str) -> bool:
    lowered = line.lower()
    return any(
        marker in lowered
        for marker in (
            "uv ",
            "playwright",
            "scripts/",
            "pnpm",
            "next_public_",
            "localhost",
            "fastapi",
        )
    )


def _query_terms(query: str) -> set[str]:
    tokens = re.findall(r"[a-zA-Z0-9_]+|[\u4e00-\u9fff]{2,}", query.lower())
    stop = {
        "how",
        "do",
        "i",
        "is",
        "the",
        "and",
        "with",
        "what",
        "does",
        "vaniscope",
        "如何",
        "并运行",
        "安装",
        "运行",
    }
    terms = {token for token in tokens if len(token) > 1 and token not in stop}
    lowered = query.lower()
    if "install" in lowered or "安装" in lowered:
        terms.update({"install", "installation", "uv", "playwright"})
    if "run" in lowered or "运行" in lowered:
        terms.update({"run", "start", "fastapi", "next", "pnpm", "scripts"})
    if "config" in lowered or "配置" in lowered:
        terms.update({"configure", "configuration", "next_public_vaniscope_api_base_url", "localhost"})
    return terms


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        deduped.append(value)
    return deduped


def _score_text(terms: set[str], text: str) -> int:
    haystack = text.lower()
    return sum(1 for term in terms if term in haystack)


def _compact_text(text: str | None, limit: int = 240) -> str:
    normalized = " ".join((text or "").split())
    if len(normalized) <= limit:
        return normalized
    return f"{normalized[: limit - 3]}..."


def _is_zh(language: str) -> bool:
    return language.lower().startswith("zh")
