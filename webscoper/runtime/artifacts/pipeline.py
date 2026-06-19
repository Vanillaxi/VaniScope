from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from webscoper.runtime.artifacts.compaction import ContextCompactor, load_jsonl
from webscoper.runtime.execution.context import WebAgentContext
from webscoper.runtime.execution.events import TaskEventSink
from webscoper.runtime.llm.reviewer import BaseLLMReportReviewer
from webscoper.runtime.artifacts.report import FinalReportBuilder
from webscoper.runtime.review.reviewer import ReportReviewer, build_review_summary_markdown
from webscoper.runtime.review.revise_loop import ReviewReviseLoop
from webscoper.runtime.review.revision import ReportReviser, ReviewRevisionPlanner
from webscoper.schemas.artifact import EvidenceItem
from webscoper.schemas.browser import PageObservation
from webscoper.schemas.runtime import PromptBuildResult
from webscoper.schemas.review import ReviewerMode
from webscoper.skills.docs_research import DocsResearchSkill
from webscoper.skills.github_issue_research import GitHubIssueResearchSkill


def persist_prompt_context(run_dir: Path, prompt_result: PromptBuildResult) -> None:
    (run_dir / "prompt_preview.md").write_text(
        prompt_result.prompt_text,
        encoding="utf-8",
    )
    (run_dir / "prompt_context.json").write_text(
        json.dumps(prompt_result.model_dump(mode="json"), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def persist_evidence_and_report(
    context: WebAgentContext,
    observation: PageObservation,
    event_sink: TaskEventSink | None = None,
    reviewer_mode: ReviewerMode = ReviewerMode.DETERMINISTIC,
    revise_attempts: int = 0,
    llm_reviewer: BaseLLMReportReviewer | None = None,
) -> None:
    evidence_items, report_text = persist_evidence_and_final_report(
        context,
        observation,
        event_sink,
    )
    persist_review_artifacts(
        context,
        report_text,
        evidence_items,
        event_sink,
    )
    persist_compaction_artifacts(context)
    if revise_attempts > 0:
        persist_revise_loop_artifacts(
            context=context,
            report_text=report_text,
            evidence_items=evidence_items,
            event_sink=event_sink,
            reviewer_mode=reviewer_mode,
            revise_attempts=revise_attempts,
            llm_reviewer=llm_reviewer,
        )


def persist_evidence_and_final_report(
    context: WebAgentContext,
    observation: PageObservation,
    event_sink: TaskEventSink | None = None,
) -> tuple[list[EvidenceItem], str]:
    evidence_items: list[EvidenceItem] = []
    if context.evidence_store is not None:
        evidence_items = context.evidence_store.list_items()
        _annotate_skill_evidence(context, evidence_items)
        context.evidence_store.write_jsonl()
        context.transcript_store.append(
            "evidence_written",
            {
                "evidence_path": str(context.run_dir / "evidence.jsonl"),
                "evidence_count": len(evidence_items),
            },
        )

    report_path = context.run_dir / "final_report.md"
    report_text = FinalReportBuilder().build_markdown(
        context.task,
        evidence_items,
        final_observation=observation,
    )
    report_path.write_text(report_text, encoding="utf-8")
    skill_result = None
    if context.task.skill_id == "docs_research":
        skill_result = DocsResearchSkill().build_result(
            context.task,
            evidence_items,
            artifact_names=[
                "final_report.md",
                "evidence.jsonl",
                "review.json",
                "skill_result.json",
                "tool_audit.jsonl",
            ],
        )
    elif context.task.skill_id == "github_issue_research":
        skill_result = GitHubIssueResearchSkill().build_result(
            context.task,
            evidence_items,
            artifact_names=[
                "final_report.md",
                "evidence.jsonl",
                "review.json",
                "skill_result.json",
                "tool_audit.jsonl",
            ],
            final_observation=observation,
        )

    if skill_result is not None:
        (context.run_dir / "skill_result.json").write_text(
            json.dumps(
                skill_result.model_dump(mode="json"),
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
    context.transcript_store.append(
        "final_report_built",
        {
            "final_report_path": str(report_path),
            "evidence_count": len(evidence_items),
            "skill_id": context.task.skill_id,
            "skill_result_path": str(context.run_dir / "skill_result.json")
            if skill_result is not None
            else None,
        },
    )
    emit_report_event(
        event_sink,
        "report_written",
        "Report written",
        {
            "run_id": context.run_id,
            "report_path": str(report_path),
            "evidence_count": len(evidence_items),
        },
    )
    return evidence_items, report_text


def _annotate_skill_evidence(
    context: WebAgentContext,
    evidence_items: list[EvidenceItem],
) -> None:
    if context.task.skill_id == "github_issue_research":
        GitHubIssueResearchSkill().annotate_evidence(evidence_items)


def persist_review_artifacts(
    context: WebAgentContext,
    report_text: str,
    evidence_items: list[EvidenceItem],
    event_sink: TaskEventSink | None = None,
):
    review_result = ReportReviewer().review(
        report_text,
        evidence_items,
        task_spec=context.task,
    )
    review_path = context.run_dir / "review.json"
    review_path.write_text(
        json.dumps(
            review_result.model_dump(mode="json"),
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    review_summary_path = context.run_dir / "review_summary.md"
    review_summary_path.write_text(
        build_review_summary_markdown(review_result),
        encoding="utf-8",
    )
    context.transcript_store.append(
        "review_completed",
        {
            "review_path": str(review_path),
            "review_summary_path": str(review_summary_path),
            "passed": review_result.passed,
            "score": review_result.score,
            "issue_count": len(review_result.issues),
        },
    )
    emit_report_event(
        event_sink,
        "review_finished",
        "Review finished",
        {
            "run_id": context.run_id,
            "review_path": str(review_path),
            "review_summary_path": str(review_summary_path),
            "passed": review_result.passed,
            "score": review_result.score,
            "issue_count": len(review_result.issues),
        },
    )
    return review_result


def persist_revise_loop_artifacts(
    *,
    context: WebAgentContext,
    report_text: str,
    evidence_items: list[EvidenceItem],
    event_sink: TaskEventSink | None,
    reviewer_mode: ReviewerMode,
    revise_attempts: int,
    llm_reviewer: BaseLLMReportReviewer | None,
) -> None:
    compact_context = read_json_object(context.run_dir / "compact_context.json")
    if llm_reviewer is not None:
        context.transcript_store.append(
            "llm_review_started",
            {"reviewer_mode": reviewer_mode.value},
        )
        emit_report_event(
            event_sink,
            "llm_review_started",
            "LLM review started",
            {"run_id": context.run_id, "reviewer_mode": reviewer_mode.value},
        )

    loop = ReviewReviseLoop(
        deterministic_reviewer=ReportReviewer(),
        revision_planner=ReviewRevisionPlanner(),
        report_reviser=ReportReviser(),
        llm_reviewer=llm_reviewer,
        max_revisions=revise_attempts,
    )
    result = loop.run(
        task_id=context.run_id,
        task_goal=context.task.raw_input,
        report_markdown=report_text,
        evidence_items=evidence_items,
        compact_context=compact_context,
        output_dir=context.run_dir,
    )
    if llm_reviewer is not None:
        context.transcript_store.append(
            "llm_review_finished",
            {
                "reviewer_mode": reviewer_mode.value,
                "passed": result.llm_review.passed if result.llm_review else None,
                "finding_count": len(result.llm_review.findings)
                if result.llm_review
                else 0,
            },
        )
        emit_report_event(
            event_sink,
            "llm_review_finished",
            "LLM review finished",
            {
                "run_id": context.run_id,
                "reviewer_mode": reviewer_mode.value,
                "passed": result.llm_review.passed if result.llm_review else None,
            },
        )

    context.transcript_store.append(
        "revision_plan_created",
        {
            "revision_plan_path": str(context.run_dir / "revision_plan.json"),
            "action_count": len(result.revision_plan.actions),
        },
    )
    context.transcript_store.append(
        "report_revised",
        {
            "revised_report_path": str(context.run_dir / "revised_report.md"),
            "revised": result.revision_result.revised,
            "applied_action_count": len(result.revision_result.applied_actions),
        },
    )
    context.transcript_store.append(
        "final_review_finished",
        {
            "final_review_path": str(context.run_dir / "final_review.json"),
            "passed": result.passed,
        },
    )
    context.transcript_store.append(
        "revise_loop_finished",
        {
            "revise_loop_path": str(context.run_dir / "revise_loop.json"),
            "artifacts": result.artifacts,
            "passed": result.passed,
        },
    )
    emit_report_event(
        event_sink,
        "revision_plan_created",
        "Revision plan created",
        {
            "run_id": context.run_id,
            "action_count": len(result.revision_plan.actions),
        },
    )
    emit_report_event(
        event_sink,
        "report_revised",
        "Report revised",
        {
            "run_id": context.run_id,
            "revised": result.revision_result.revised,
            "applied_action_count": len(result.revision_result.applied_actions),
        },
    )
    emit_report_event(
        event_sink,
        "final_review_finished",
        "Final review finished",
        {"run_id": context.run_id, "passed": result.passed},
    )
    emit_report_event(
        event_sink,
        "revise_loop_finished",
        "Revise loop finished",
        {"run_id": context.run_id, "artifacts": result.artifacts},
    )


def persist_compaction_artifacts(context: WebAgentContext) -> None:
    run_dir = context.run_dir
    compactor = ContextCompactor()
    risk_report = read_json_object(run_dir / "risk_report.json")
    result = compactor.compact(
        task_id=context.run_id,
        task_goal=context.task.raw_input,
        transcript_events=load_jsonl(context.transcript_store.transcript_path),
        trace_events=load_jsonl(context.trace_recorder.trace_path),
        evidence_items=context.evidence_store.list_items()
        if context.evidence_store is not None
        else [],
        recovery_attempts=load_jsonl(run_dir / "recovery.jsonl"),
        approval_requests=load_jsonl(run_dir / "approvals.jsonl"),
        risk_report=risk_report,
    )
    compactor.write_artifacts(result, run_dir)
    context.transcript_store.append(
        "compaction_written",
        {
            "compact_context_path": str(run_dir / "compact_context.json"),
            "compact_summary_path": str(run_dir / "compact_summary.md"),
            "compacted": result.compacted,
            "before_counts": result.before_counts,
            "after_counts": result.after_counts,
            "warning_count": len(result.warnings),
        },
    )


def read_json_object(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def emit_report_event(
    event_sink: TaskEventSink | None,
    kind: str,
    message: str,
    payload: dict[str, Any],
) -> None:
    if event_sink is None:
        return
    try:
        event_sink(kind, message, payload)
    except Exception:
        return
