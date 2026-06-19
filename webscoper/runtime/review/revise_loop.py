from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from webscoper.runtime.llm.reviewer import BaseLLMReportReviewer
from webscoper.runtime.review.reviewer import ReportReviewer
from webscoper.runtime.review.revision import ReportReviser, ReviewRevisionPlanner
from webscoper.schemas.artifact import EvidenceItem
from webscoper.schemas.review import (
    LLMReviewRequest,
    RevisionPlan,
    ReviseLoopResult,
)


class ReviewReviseLoop:
    def __init__(
        self,
        deterministic_reviewer: ReportReviewer,
        revision_planner: ReviewRevisionPlanner,
        report_reviser: ReportReviser,
        llm_reviewer: BaseLLMReportReviewer | None = None,
        max_revisions: int = 1,
    ) -> None:
        self.deterministic_reviewer = deterministic_reviewer
        self.revision_planner = revision_planner
        self.report_reviser = report_reviser
        self.llm_reviewer = llm_reviewer
        self.max_revisions = max(0, max_revisions)

    def run(
        self,
        *,
        task_id: str | None,
        task_goal: str | None,
        report_markdown: str,
        evidence_items: list[EvidenceItem],
        compact_context: dict[str, Any] | None = None,
        output_dir: Path | None = None,
    ) -> ReviseLoopResult:
        initial_review = self.deterministic_reviewer.review(
            report_markdown,
            evidence_items,
        )
        llm_review = None
        if self.llm_reviewer is not None:
            llm_review = self.llm_reviewer.review(
                LLMReviewRequest(
                    task_id=task_id,
                    task_goal=task_goal,
                    report_markdown=report_markdown,
                    evidence_items=[
                        item.model_dump(mode="json") for item in evidence_items
                    ],
                    compact_context=compact_context,
                    deterministic_review=initial_review.model_dump(mode="json"),
                    instructions=[
                        "Review strictly against available evidence ids.",
                        "Do not invent evidence or claims.",
                    ],
                )
            )

        plan = (
            self.revision_planner.build_plan(
                report_markdown=report_markdown,
                deterministic_review=initial_review,
                llm_review=llm_review,
                evidence_items=evidence_items,
            )
            if self.max_revisions > 0
            else RevisionPlan(actions=[], summary="Revision attempts disabled.")
        )
        revision = self.report_reviser.apply_plan(
            report_markdown,
            plan,
            evidence_items,
        )
        final_review = self.deterministic_reviewer.review(
            revision.revised_report_markdown,
            evidence_items,
        )

        result = ReviseLoopResult(
            task_id=task_id,
            initial_review=initial_review.model_dump(mode="json"),
            llm_review=llm_review,
            revision_plan=plan,
            revision_result=revision,
            final_review=final_review.model_dump(mode="json"),
            passed=final_review.passed,
            artifacts=[],
            metadata={
                "max_revisions": self.max_revisions,
                "revised": revision.revised,
            },
        )
        if output_dir is not None:
            result = _write_artifacts(result, output_dir)
        return result


def _write_artifacts(
    result: ReviseLoopResult,
    output_dir: Path,
) -> ReviseLoopResult:
    output_dir.mkdir(parents=True, exist_ok=True)
    artifacts: list[str] = []
    if result.llm_review is not None:
        _write_json(output_dir / "llm_review.json", result.llm_review.model_dump(mode="json"))
        artifacts.append("llm_review.json")
    _write_json(
        output_dir / "revision_plan.json",
        result.revision_plan.model_dump(mode="json"),
    )
    artifacts.append("revision_plan.json")
    (output_dir / "revised_report.md").write_text(
        result.revision_result.revised_report_markdown,
        encoding="utf-8",
    )
    artifacts.append("revised_report.md")
    _write_json(output_dir / "final_review.json", result.final_review)
    artifacts.append("final_review.json")
    updated = result.model_copy(update={"artifacts": artifacts + ["revise_loop.json"]})
    _write_json(output_dir / "revise_loop.json", updated.model_dump(mode="json"))
    return updated


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
