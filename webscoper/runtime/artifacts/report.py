from __future__ import annotations

import re

from webscoper.runtime.localization import is_zh, normalize_locale
from webscoper.schemas.artifact import EvidenceItem
from webscoper.schemas.browser import PageObservation
from webscoper.schemas.task import TaskSpec
from webscoper.skills.docs_research import DocsResearchSkill
from webscoper.skills.github_issue_research import GitHubIssueResearchSkill


class FinalReportBuilder:
    def build_markdown(
        self,
        task_spec: TaskSpec,
        evidence_items: list[EvidenceItem],
        final_observation: PageObservation | None = None,
    ) -> str:
        if task_spec.skill_id == "docs_research":
            return DocsResearchSkill().build_report(
                task_spec,
                evidence_items,
                final_observation=final_observation,
            )
        if task_spec.skill_id == "github_issue_research":
            return GitHubIssueResearchSkill().build_report(
                task_spec,
                evidence_items,
                final_observation=final_observation,
            )

        language = normalize_locale(
            task_spec.report_language
            or task_spec.requested_output_language
            or task_spec.display_language
            or task_spec.language
        )
        labels = _labels(language)
        findings = _findings(task_spec, evidence_items, final_observation, language)
        analysis = _analysis(task_spec, evidence_items, final_observation, language)
        details = _details(task_spec, evidence_items, final_observation, language)
        limitations = _limitations(final_observation, evidence_items, language)
        lines = [
            f"# {labels['title']}",
            "",
            f"## {labels['overview']}",
            "",
            f"- {labels['task_id']}: {task_spec.task_id}",
            f"- {labels['goal']}: {_goal(task_spec)}",
            f"- {labels['target_url']}: {task_spec.target_url}",
            f"- {labels['output_language']}: {labels['language_name']}",
            "",
            f"## {labels['findings']}",
            "",
            findings,
            "",
            f"## {labels['analysis']}",
            "",
            analysis,
            "",
            f"## {labels['details']}",
            "",
        ]
        lines.extend(details)
        lines.extend(["", f"## {labels['evidence']}", ""])
        if evidence_items:
            lines.extend(_evidence_lines(evidence_items, language))
        else:
            lines.append(f"- {labels['no_evidence']}")

        lines.extend(
            [
                "",
                f"## {labels['risks']}",
                "",
                limitations,
                "",
                f"## {labels['next_steps']}",
                "",
                labels["next_step"],
                "",
            ]
        )
        return "\n".join(lines)


def _goal(task_spec: TaskSpec) -> str:
    return (
        task_spec.goal
        or task_spec.query
        or task_spec.research_goal
        or task_spec.raw_input
    )


def _findings(
    task_spec: TaskSpec,
    evidence_items: list[EvidenceItem],
    final_observation: PageObservation | None,
    language: str,
) -> str:
    refs = _evidence_refs(evidence_items)
    source = _source_title(final_observation, evidence_items) or task_spec.target_url
    if not evidence_items and final_observation is None:
        return (
            "当前没有可用的最终页面观察或证据，因此无法形成可靠结论。"
            if is_zh(language)
            else "No final observation or evidence is available, so no reliable conclusion can be drawn."
        )
    names = _proper_names(evidence_items, final_observation)
    if is_zh(language):
        focus = f"页面“{source}”" if source else "当前页面"
        if names:
            return (
                f"{focus}的可见内容显示，关键信息包括 {', '.join(names[:6])}。"
                f"这些结论基于已采集证据{refs}，未使用证据之外的信息。"
            )
        return f"{focus}已有可见证据可用于回答任务目标，结论基于已采集证据{refs}。"
    if names:
        return (
            f"The visible content for {source} shows key information including "
            f"{', '.join(names[:6])}. These conclusions are based on captured evidence{refs}."
        )
    return f"The task can be summarized from captured evidence{refs}."


def _details(
    task_spec: TaskSpec,
    evidence_items: list[EvidenceItem],
    final_observation: PageObservation | None,
    language: str,
) -> list[str]:
    details: list[str] = []
    source_url = _source_url(task_spec, evidence_items, final_observation)
    page_title = _source_title(final_observation, evidence_items)
    if is_zh(language):
        if page_title:
            details.append(f"- 页面标题：{page_title}{_evidence_refs(evidence_items[:1])}")
        details.append(f"- 目标页面：{source_url}")
        for item in evidence_items[:5]:
            summary = _evidence_summary_text(item, language)
            if summary:
                details.append(f"- {summary} [{item.evidence_id}]")
        return details or ["- 当前证据不足，无法提取更多关键信息。"]
    if page_title:
        details.append(f"- Page title: {page_title}{_evidence_refs(evidence_items[:1])}")
    details.append(f"- Target page: {source_url}")
    for item in evidence_items[:5]:
        summary = _evidence_summary_text(item, language)
        if summary:
            details.append(f"- {summary} [{item.evidence_id}]")
    return details or ["- There is not enough evidence to extract additional important details."]


def _analysis(
    task_spec: TaskSpec,
    evidence_items: list[EvidenceItem],
    final_observation: PageObservation | None,
    language: str,
) -> str:
    refs = _evidence_refs(evidence_items)
    source = _source_title(final_observation, evidence_items) or task_spec.target_url
    names = _proper_names(evidence_items, final_observation)
    goal = _goal(task_spec)
    if not evidence_items and final_observation is None:
        return (
            "当前缺少可验证材料，因此只能判断任务尚未形成可靠分析结果。"
            if is_zh(language)
            else "There is not enough verifiable material to produce a reliable interpretation yet."
        )
    if is_zh(language):
        if names:
            return (
                f"从任务目标“{goal}”看，{source} 的公开内容主要围绕 "
                f"{', '.join(names[:4])} 展开。更合理的解读不是罗列页面字段，"
                f"而是把这些可见信息视为回答任务目标的证据集合；当前结论应以这些证据为边界{refs}。"
            )
        return f"从已采集材料看，{source} 能支持任务目标的初步判断，但结论范围应限制在可见证据内{refs}。"
    if names:
        return (
            f"For the goal {goal!r}, {source} is best interpreted through the visible signals around "
            f"{', '.join(names[:4])}. The useful conclusion is not the raw page fields themselves, "
            f"but what those fields collectively indicate within the captured evidence boundary{refs}."
        )
    return f"The captured material supports a limited interpretation of {source}; conclusions should stay within the visible evidence boundary{refs}."


def _limitations(
    final_observation: PageObservation | None,
    evidence_items: list[EvidenceItem],
    language: str,
) -> str:
    partial = final_observation is None or not evidence_items
    if is_zh(language):
        if partial:
            return "本报告仅基于当前可用的页面观察和证据生成；如果页面加载不完整，结论可能需要复核。"
        return "本报告仅基于运行期间采集的可见页面证据生成；页面后续变化不在本次结论范围内。"
    if partial:
        return "This report is based only on the available page observation and evidence; conclusions may need review if the page loaded partially."
    return "This report is based only on visible page evidence captured during the run; later page changes are outside this report."


def _evidence_lines(evidence_items: list[EvidenceItem], language: str) -> list[str]:
    lines: list[str] = []
    for item in evidence_items:
        source = item.source_url or ("未知来源" if is_zh(language) else "unknown source")
        text = _compact(item.text, 180)
        if item.kind == "page_observation":
            label = "页面观察" if is_zh(language) else "Page observation"
        elif item.kind == "action_result":
            label = "操作结果" if is_zh(language) else "Action result"
        elif item.kind == "text_excerpt":
            label = "文本证据" if is_zh(language) else "Text excerpt"
        else:
            label = item.kind
        connector = "来自" if is_zh(language) else "from"
        lines.append(f"- [{item.evidence_id}] {label} {connector} {source}: {text}")
    return lines


def _evidence_refs(evidence_items: list[EvidenceItem]) -> str:
    if not evidence_items:
        return ""
    refs = ", ".join(f"[{item.evidence_id}]" for item in evidence_items[:3])
    return f" {refs}"


def _source_url(
    task_spec: TaskSpec,
    evidence_items: list[EvidenceItem],
    final_observation: PageObservation | None,
) -> str:
    if final_observation is not None and final_observation.url:
        return final_observation.url
    for item in evidence_items:
        if item.source_url:
            return item.source_url
    return task_spec.target_url


def _source_title(
    final_observation: PageObservation | None,
    evidence_items: list[EvidenceItem],
) -> str | None:
    if final_observation is not None and final_observation.title:
        return final_observation.title
    for item in evidence_items:
        if item.page_title:
            return item.page_title
    return None


def _proper_names(
    evidence_items: list[EvidenceItem],
    final_observation: PageObservation | None,
) -> list[str]:
    text = " ".join(
        [final_observation.title if final_observation else ""]
        + [item.page_title or "" for item in evidence_items]
        + [item.text or "" for item in evidence_items[:5]]
    )
    candidates = re.findall(
        r"\b[A-Z][A-Za-z0-9_.-]{2,}(?:/[A-Za-z0-9_.-]+)?\b|[\u4e00-\u9fff]{2,}",
        text,
    )
    stop = {"Skip", "Navigation", "Menu", "Search", "Sign", "Overview", "Result"}
    output: list[str] = []
    for candidate in candidates:
        if candidate in stop or candidate in output:
            continue
        output.append(candidate)
    return output[:12]


def _evidence_summary_text(item: EvidenceItem, language: str) -> str:
    source = item.page_title or item.source_url or (
        "未知来源" if is_zh(language) else "unknown source"
    )
    text = _compact(item.text, 160)
    if is_zh(language):
        if item.kind in {"screenshot", "page_screenshot"}:
            return f"{source} 提供了截图证据。"
        return f"{source} 中可见：{text}" if text else f"{source} 提供了页面证据。"
    if item.kind in {"screenshot", "page_screenshot"}:
        return f"{source} provides screenshot evidence."
    return f"{source} shows: {text}" if text else f"{source} provides page evidence."


def _compact(text: str | None, limit: int) -> str:
    value = " ".join((text or "").split())
    if len(value) <= limit:
        return value
    return f"{value[: limit - 3]}..."


def _labels(language: str) -> dict[str, str]:
    if is_zh(language):
        return {
            "title": "VaniScope 任务报告",
            "overview": "任务概览",
            "findings": "核心结论",
            "analysis": "分析解读",
            "details": "关键信息",
            "evidence": "证据链",
            "risks": "风险与限制",
            "next_steps": "后续建议",
            "task_id": "任务 ID",
            "goal": "目标",
            "target_url": "目标页面",
            "output_language": "输出语言",
            "language_name": "中文",
            "no_evidence": "暂无可用证据。",
            "next_step": "建议在需要更高置信度时重新运行任务，并确认页面已完整加载。",
        }
    return {
        "title": "VaniScope Task Report",
        "overview": "Task Overview",
        "findings": "Key Findings",
        "analysis": "Analysis",
        "details": "Important Details",
        "evidence": "Evidence",
        "risks": "Risks and Limitations",
        "next_steps": "Next Steps",
        "task_id": "Task ID",
        "goal": "Goal",
        "target_url": "Target URL",
        "output_language": "Output language",
        "language_name": "English",
        "no_evidence": "No evidence was captured.",
        "next_step": "Rerun the task with a fully loaded page if higher confidence is required.",
    }
