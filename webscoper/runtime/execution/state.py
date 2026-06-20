from __future__ import annotations

from webscoper.runtime.execution.context import WebAgentContext
from webscoper.schemas.browser import PageObservation
from webscoper.schemas.task import TaskSpec


def task_payload(task: TaskSpec) -> dict:
    return {
        "task_id": task.task_id,
        "task_type": task.task_type,
        "target_url": task.target_url,
        "has_action": task.action is not None,
        "tags": task.tags,
        "budget": task.budget.model_dump(mode="json"),
        "safety": task.safety.model_dump(mode="json"),
    }


def state_payload(context: WebAgentContext) -> dict:
    return {
        "task_id": context.task.task_id,
        "run_id": context.run_id,
        "run_dir": str(context.run_dir),
        "state": context.state.model_dump(mode="json"),
    }


def status_from_loop_error(error_type: str | None) -> str | None:
    if error_type == "RISK_APPROVAL_REQUIRED":
        return "requires_approval"
    if error_type in {
        "RISK_BLOCKED",
        "PUBLIC_WEB_BLOCKED",
        "UNKNOWN_TOOL",
        "TOOL_DISABLED",
        "TOOL_DANGEROUS",
    }:
        return "blocked"
    return None


def observation_summary(observation: PageObservation) -> dict:
    return {
        "url": observation.url,
        "title": observation.title,
        "risk_signals_count": len(observation.risk_signals),
        "interactive_elements_count": len(observation.interactive_elements),
        "screenshot_path": observation.screenshot_path,
    }
