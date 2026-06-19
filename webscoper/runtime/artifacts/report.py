from __future__ import annotations

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

        lines = [
            "# VaniScope Task Report",
            "",
            "## Task",
            "",
            f"- task_id: {task_spec.task_id}",
            f"- input: {task_spec.raw_input}",
            f"- target_url: {task_spec.target_url}",
            "",
            "## Result",
            "",
            _result_line(final_observation, evidence_items),
            "",
            "## Evidence",
            "",
        ]
        if evidence_items:
            lines.extend(_evidence_lines(evidence_items))
        else:
            lines.append("- No evidence was captured.")

        lines.extend(
            [
                "",
                "## Notes",
                "",
                "This report was generated deterministically from captured runtime evidence.",
                "",
            ]
        )
        return "\n".join(lines)


def _result_line(
    final_observation: PageObservation | None,
    evidence_items: list[EvidenceItem],
) -> str:
    if final_observation is None:
        return "No final observation was available."
    summary = final_observation.visible_text_summary.replace("\n", " ")
    refs = _evidence_refs(evidence_items)
    return (
        f"Final page: {final_observation.title} "
        f"({final_observation.url}); visible text: {summary}{refs}"
    )


def _evidence_lines(evidence_items: list[EvidenceItem]) -> list[str]:
    lines: list[str] = []
    for item in evidence_items:
        source = item.source_url or "unknown source"
        text = (item.text or "").replace("\n", " ")
        if len(text) > 180:
            text = f"{text[:177]}..."
        if item.kind == "page_observation":
            lines.append(f"- [{item.evidence_id}] Page observation from {source}: {text}")
        elif item.kind == "action_result":
            lines.append(f"- [{item.evidence_id}] Action result from {source}: {text}")
        elif item.kind == "text_excerpt":
            lines.append(f"- [{item.evidence_id}] Text excerpt from {source}: {text}")
        else:
            lines.append(f"- [{item.evidence_id}] {item.kind} from {source}: {text}")
    return lines


def _evidence_refs(evidence_items: list[EvidenceItem]) -> str:
    if not evidence_items:
        return ""
    refs = ", ".join(f"[{item.evidence_id}]" for item in evidence_items[:3])
    return f" Evidence: {refs}."
