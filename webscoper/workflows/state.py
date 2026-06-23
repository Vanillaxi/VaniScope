from __future__ import annotations

from typing import Any, TypedDict


class VaniScopeGraphState(TypedDict, total=False):
    task_id: str
    task_goal: str | None
    request: dict[str, Any]
    run_dir: str
    thread_id: str
    workspace: str | None
    skill_id: str | None
    task_type: str | None
    skill_context: dict[str, Any] | None
    skill_plan: dict[str, Any] | None
    skill_session: dict[str, Any] | None

    prompt_markdown: str | None
    prompt_context: dict[str, Any] | None

    planner_mode: str
    plan: dict[str, Any] | None
    validation_result: dict[str, Any] | None

    execution_result: dict[str, Any] | None
    final_observation: dict[str, Any] | None
    langgraph_interrupt: dict[str, Any] | None
    langgraph_resume: dict[str, Any] | None

    evidence_items: list[dict[str, Any]]
    report_markdown: str | None
    review_result: dict[str, Any] | None
    compaction_result: dict[str, Any] | None
    revise_loop_result: dict[str, Any] | None

    artifacts: list[str]
    status: str
    error: str | None
    events: list[dict[str, Any]]
    metadata: dict[str, Any]
