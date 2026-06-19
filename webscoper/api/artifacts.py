from __future__ import annotations

from pathlib import Path

from webscoper.api.schemas import (
    TaskArtifactContentResponse,
    TaskArtifactListResponse,
)


ARTIFACT_ALLOWLIST = {
    "events.jsonl",
    "recovery.jsonl",
    "approvals.jsonl",
    "pending.jsonl",
    "risk_report.json",
    "tool_audit.jsonl",
    "trace.jsonl",
    "transcript.jsonl",
    "evidence.jsonl",
    "compact_context.json",
    "compact_summary.md",
    "final_report.md",
    "review.json",
    "review_summary.md",
    "skill_result.json",
    "llm_review.json",
    "llm_calls.jsonl",
    "revision_plan.json",
    "revised_report.md",
    "final_review.json",
    "revise_loop.json",
    "dry_run_result.json",
    "prompt_preview.md",
    "prompt_context.json",
    "workflow_state.json",
    "langgraph_interrupts.jsonl",
    "score.json",
    "report.md",
}


def list_existing_artifacts(run_dir: Path) -> list[str]:
    return [
        artifact
        for artifact in sorted(ARTIFACT_ALLOWLIST)
        if (run_dir / artifact).is_file()
    ]


def list_task_artifacts(service, task_id: str) -> TaskArtifactListResponse:
    run_dir = service._existing_run_dir(task_id)
    return TaskArtifactListResponse(
        task_id=task_id,
        artifacts=list_existing_artifacts(run_dir),
    )


def read_task_artifact(
    service,
    task_id: str,
    artifact_name: str,
) -> TaskArtifactContentResponse:
    if artifact_name not in ARTIFACT_ALLOWLIST:
        raise ValueError(f"Artifact is not allowed: {artifact_name}")
    run_dir = service._existing_run_dir(task_id)
    artifact_path = (run_dir / artifact_name).resolve()
    if artifact_path.parent != run_dir.resolve():
        raise ValueError("Artifact path escapes task run directory.")
    if not artifact_path.exists() or not artifact_path.is_file():
        raise FileNotFoundError(f"Artifact not found: {artifact_name}")
    return TaskArtifactContentResponse(
        task_id=task_id,
        artifact_name=artifact_name,
        content=artifact_path.read_text(encoding="utf-8"),
    )


def write_task_artifacts(service, task_id: str) -> None:
    run_dir = service._run_dir(task_id)
    try:
        service.event_store.write_jsonl(task_id, run_dir / "events.jsonl")
        service.approval_store.write_jsonl_for_task(task_id, run_dir / "approvals.jsonl")
        service.approval_store.write_risk_report(task_id, run_dir / "risk_report.json")
        service.pending_manager.write_jsonl(task_id, run_dir / "pending.jsonl")
        adapter = service._langgraph_adapters.get(task_id)
        if adapter is not None:
            adapter.approval_bridge.write_jsonl_for_task(
                task_id,
                run_dir / "langgraph_interrupts.jsonl",
            )
    except Exception:
        pass
