from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from webscoper.runtime.control import TaskControlStore
from webscoper.runtime.execution.events import TaskEventSink
from webscoper.runtime.safety.approvals import ApprovalStore
from webscoper.schemas.runtime import BudgetContext


class BudgetApprovalRequired(RuntimeError):
    def __init__(self, approval_id: str) -> None:
        super().__init__(f"LLM budget approval required: {approval_id}")
        self.approval_id = approval_id


class BudgetHardLimitExceeded(RuntimeError):
    pass


@dataclass(frozen=True)
class BudgetEstimate:
    prompt_tokens_next_call: int
    completion_tokens_next_call: int
    prompt_tokens_so_far: int
    completion_tokens_so_far: int
    llm_calls_so_far: int
    estimated_cost_so_far: float
    estimated_cost_next_call: float

    @property
    def prompt_tokens_with_next(self) -> int:
        return self.prompt_tokens_so_far + self.prompt_tokens_next_call

    @property
    def completion_tokens_with_next(self) -> int:
        return self.completion_tokens_so_far + self.completion_tokens_next_call

    @property
    def cost_with_next(self) -> float:
        return self.estimated_cost_so_far + self.estimated_cost_next_call


def decide_budget(
    budget: BudgetContext,
    estimate: BudgetEstimate,
    *,
    continue_for_task: bool = False,
    per_call_compacted: bool = False,
) -> str:
    if estimate.llm_calls_so_far >= budget.max_llm_calls_per_task:
        return "denied"
    if estimate.prompt_tokens_next_call > budget.max_prompt_tokens_per_call:
        return "compaction_required" if budget.enable_auto_compaction and not per_call_compacted else "hard_limit_exceeded"
    if estimate.prompt_tokens_with_next > budget.hard_prompt_tokens_per_task:
        return "hard_limit_exceeded"
    if estimate.completion_tokens_with_next > budget.max_completion_tokens_per_task:
        return "hard_limit_exceeded"
    if budget.hard_cost_usd_per_task and estimate.cost_with_next > budget.hard_cost_usd_per_task:
        return "hard_limit_exceeded"
    if (
        budget.enable_budget_approval
        and not continue_for_task
        and (
            estimate.prompt_tokens_with_next > budget.approval_prompt_tokens_per_task
            or estimate.cost_with_next > budget.approval_cost_usd_per_task
        )
    ):
        return "approval_required"
    if (
        estimate.prompt_tokens_with_next > budget.soft_prompt_tokens_per_task
        or estimate.cost_with_next > budget.soft_cost_usd_per_task
    ):
        return "warning"
    return "allowed"


def build_estimate(
    *,
    prompt_tokens_next_call: int,
    max_completion_tokens_next_call: int,
    prompt_tokens_so_far: int,
    completion_tokens_so_far: int,
    llm_calls_so_far: int,
) -> BudgetEstimate:
    return BudgetEstimate(
        prompt_tokens_next_call=prompt_tokens_next_call,
        completion_tokens_next_call=max_completion_tokens_next_call,
        prompt_tokens_so_far=prompt_tokens_so_far,
        completion_tokens_so_far=completion_tokens_so_far,
        llm_calls_so_far=llm_calls_so_far,
        estimated_cost_so_far=_estimate_cost_usd(
            prompt_tokens_so_far,
            completion_tokens_so_far,
        ),
        estimated_cost_next_call=_estimate_cost_usd(
            prompt_tokens_next_call,
            max_completion_tokens_next_call,
        ),
    )


def maybe_create_budget_approval(
    *,
    approval_store: ApprovalStore | None,
    control_store: TaskControlStore | None,
    event_sink: TaskEventSink | None,
    task_id: str,
    run_dir: Path | None,
    provider: str,
    model: str,
    purpose: str,
    user_goal: str | None,
    budget: BudgetContext,
    estimate: BudgetEstimate,
) -> str | None:
    if approval_store is None:
        return None
    existing = [
        approval
        for approval in approval_store.list_for_task(task_id)
        if approval.status == "pending"
        and approval.metadata.get("approval_type") == "llm_budget"
    ]
    if existing:
        return existing[-1].approval_id
    payload = {
        "approval_type": "llm_budget",
        "current_llm_calls": estimate.llm_calls_so_far,
        "max_calls_per_task": budget.max_llm_calls_per_task,
        "estimated_prompt_tokens_so_far": estimate.prompt_tokens_so_far,
        "estimated_completion_tokens_so_far": estimate.completion_tokens_so_far,
        "estimated_prompt_tokens_next_call": estimate.prompt_tokens_next_call,
        "estimated_completion_tokens_next_call": estimate.completion_tokens_next_call,
        "estimated_cost_so_far": round(estimate.estimated_cost_so_far, 6),
        "estimated_cost_next_call": round(estimate.estimated_cost_next_call, 6),
        "provider": provider,
        "model": model,
        "current_step": purpose,
        "user_goal": user_goal,
        "current_evidence_count": _evidence_count(run_dir),
        "suggested_options": [
            "continue_once",
            "continue_for_task",
            "continue_with_compaction",
            "stop_and_summarize",
            "cancel_task",
        ],
    }
    approval = approval_store.create_request(
        task_id=task_id,
        reason="This task is estimated to exceed the configured LLM token/cost budget.",
        risk_level="medium",
        tool_name="llm_budget",
        action_type="budget_approval",
        target_hint=purpose,
        metadata=payload,
    )
    if run_dir is not None:
        approval_store.write_jsonl_for_task(task_id, run_dir / "approvals.jsonl")
    _emit(
        event_sink,
        "budget_approval_required",
        "LLM budget approval required",
        {
            "run_id": task_id,
            "approval_id": approval.approval_id,
            "approval_request": approval.model_dump(mode="json"),
        },
    )
    if control_store is not None:
        control_store.write_jsonl(task_id, (run_dir or Path(".")) / "user_control.jsonl")
    return approval.approval_id


def append_budget_decision(
    run_dir: Path | None,
    *,
    task_id: str,
    decision: str,
    provider: str,
    model: str,
    purpose: str,
    budget: BudgetContext,
    estimate: BudgetEstimate,
    compaction_applied: bool,
    approval_id: str | None = None,
) -> None:
    if run_dir is None:
        return
    record = {
        "timestamp": _utc_now(),
        "task_id": task_id,
        "decision": decision,
        "provider": provider,
        "model": model,
        "purpose": purpose,
        "estimated_prompt_tokens": estimate.prompt_tokens_next_call,
        "max_prompt_tokens_per_call": budget.max_prompt_tokens_per_call,
        "prompt_tokens_so_far": estimate.prompt_tokens_so_far,
        "completion_tokens_so_far": estimate.completion_tokens_so_far,
        "approval_threshold": budget.approval_prompt_tokens_per_task,
        "hard_threshold": budget.hard_prompt_tokens_per_task,
        "estimated_cost_so_far": round(estimate.estimated_cost_so_far, 6),
        "estimated_cost_next_call": round(estimate.estimated_cost_next_call, 6),
        "compaction_applied": compaction_applied,
        "approval_id": approval_id,
    }
    run_dir.mkdir(parents=True, exist_ok=True)
    with (run_dir / "budget_decisions.jsonl").open("a", encoding="utf-8") as file:
        file.write(json.dumps(record, ensure_ascii=False) + "\n")
    (run_dir / "prompt_budget_estimate.json").write_text(
        json.dumps(record, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def emit_budget_checked(
    event_sink: TaskEventSink | None,
    *,
    task_id: str,
    decision: str,
    provider: str,
    model: str,
    budget: BudgetContext,
    estimate: BudgetEstimate,
    compaction_applied: bool,
) -> None:
    _emit(
        event_sink,
        "budget_checked",
        "LLM budget checked",
        {
            "run_id": task_id,
            "decision": decision,
            "estimated_prompt_tokens": estimate.prompt_tokens_next_call,
            "max_prompt_tokens_per_call": budget.max_prompt_tokens_per_call,
            "prompt_tokens_so_far": estimate.prompt_tokens_so_far,
            "approval_threshold": budget.approval_prompt_tokens_per_task,
            "hard_threshold": budget.hard_prompt_tokens_per_task,
            "provider": provider,
            "model": model,
            "compaction_applied": compaction_applied,
        },
    )


def compact_llm_messages(messages: list[Any], *, max_prompt_tokens: int) -> list[Any]:
    if not messages:
        return messages
    char_budget = max(800, max_prompt_tokens * 4)
    per_message_budget = max(400, char_budget // len(messages))
    compacted = []
    for message in messages:
        content = getattr(message, "content", "")
        if len(content) > per_message_budget:
            content = (
                content[: per_message_budget // 2]
                + "\n\n[...prompt context compacted...]\n\n"
                + content[-per_message_budget // 2 :]
            )
        compacted.append(message.model_copy(update={"content": content}))
    return compacted


def _estimate_cost_usd(prompt_tokens: int, completion_tokens: int) -> float:
    return (prompt_tokens * 0.000002) + (completion_tokens * 0.000006)


def _evidence_count(run_dir: Path | None) -> int:
    if run_dir is None:
        return 0
    evidence_path = run_dir / "evidence.jsonl"
    if not evidence_path.exists():
        return 0
    try:
        return sum(1 for line in evidence_path.read_text(encoding="utf-8").splitlines() if line.strip())
    except OSError:
        return 0


def _emit(
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


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()
