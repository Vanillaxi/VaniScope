from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from webscoper.runtime.execution.handler import WebAgentExecutionHandler
from webscoper.runtime.prompt.reminders import RuntimeReminderStore
from webscoper.schemas.browser import ActionContract, ExpectedEffect, PageObservation
from webscoper.schemas.task import TaskSpec
from webscoper.schemas.workflow import WorkflowRunResult


@dataclass
class TaskRunOutput:
    task: TaskSpec
    observation: PageObservation
    handler: WebAgentExecutionHandler


def run_browser_task_sync(
    url: str,
    click: str | None = None,
    expect: str | None = None,
    task_type: str = "browser_task",
    skill_id: str | None = None,
    query: str | None = None,
    research_goal: str | None = None,
    language: str = "auto",
    planner: str = "deterministic",
    workspace: str | Path | None = None,
    reminders: list[str] | None = None,
    output_root: Path = Path("runs"),
    headed: bool = False,
    model_override: str | None = None,
    repair_attempts: int = 0,
    reviewer: str = "deterministic",
    revise_attempts: int = 0,
    llm_config: str | Path | None = None,
    llm_provider: str | None = None,
    task_id: str = "cli_task",
    reminder_source: str = "runtime",
) -> TaskRunOutput:
    task = build_task_spec(
        url=url,
        click=click,
        expect=expect,
        task_type=task_type,
        skill_id=skill_id,
        query=query,
        research_goal=research_goal,
        language=language,
        task_id=task_id,
    )
    reminder_store = RuntimeReminderStore()
    for reminder in reminders or []:
        reminder_store.add(reminder, source=reminder_source)

    handler = WebAgentExecutionHandler(
        output_root=output_root,
        headless=not headed,
        workspace=Path(workspace) if workspace else None,
        runtime_reminders=reminder_store,
        planner_mode=planner,
        model_override=model_override,
        repair_attempts=repair_attempts,
        reviewer_mode=reviewer,
        revise_attempts=revise_attempts,
        llm_config_path=llm_config_path(planner, llm_config, reviewer=reviewer),
        llm_provider=llm_provider,
    )
    workflow_result = run_langgraph_workflow_sync(handler, task)
    if workflow_result.error and workflow_result.status == "failed":
        raise RuntimeError(workflow_result.error)
    observation = _last_observation_from_handler(handler)
    return TaskRunOutput(task=task, observation=observation, handler=handler)


class TaskRunner:
    def __init__(self, handler: WebAgentExecutionHandler) -> None:
        self.handler = handler

    def run(self, task: TaskSpec) -> TaskRunOutput:
        result = run_langgraph_workflow_sync(self.handler, task)
        if result.error and result.status == "failed":
            raise RuntimeError(result.error)
        observation = _last_observation_from_handler(self.handler)
        return TaskRunOutput(task=task, observation=observation, handler=self.handler)


def run_langgraph_workflow_sync(
    handler: WebAgentExecutionHandler,
    task: TaskSpec,
) -> WorkflowRunResult:
    try:
        from webscoper.workflows.langgraph_adapter import LangGraphWorkflowAdapter
    except ImportError as exc:
        raise RuntimeError(
            "LangGraph workflow requested but langgraph is not installed"
        ) from exc
    return LangGraphWorkflowAdapter(handler).run(task)


def _last_observation_from_handler(handler: WebAgentExecutionHandler) -> PageObservation:
    loop_result = handler.last_loop_result
    if loop_result is not None and loop_result.final_output:
        observation_payload = loop_result.final_output.get("observation")
        if isinstance(observation_payload, dict):
            return PageObservation.model_validate(observation_payload)
    context = handler.last_context
    if context is not None and context.state.status in {
        "requires_approval",
        "blocked",
    }:
        raise RuntimeError(
            context.state.error_message or f"Task ended with status {context.state.status}."
        )
    raise RuntimeError("LangGraph workflow completed without a final observation.")


def build_task_spec(
    url: str,
    click: str | None = None,
    expect: str | None = None,
    task_type: str = "browser_task",
    skill_id: str | None = None,
    query: str | None = None,
    research_goal: str | None = None,
    expected_output: str | None = None,
    constraints: list[str] | None = None,
    language: str = "auto",
    task_id: str = "cli_task",
) -> TaskSpec:
    return TaskSpec(
        task_id=task_id,
        raw_input=raw_input(url, click, expect, query or research_goal),
        task_type=task_type,
        skill_id=skill_id,
        target_url=as_url(url),
        query=query,
        research_goal=research_goal,
        expected_output=expected_output,
        constraints=constraints or [],
        language=language,
        action=action(click, expect) if click else None,
        expected_effect=expected_effect(expect) if expect else None,
        tags=["cli"],
    )


def action(click: str, expect: str | None) -> ActionContract:
    return ActionContract(
        action_type="click",
        intent=f"Click {click}",
        target_hint=click,
        preferred_roles=["button", "link"],
        preconditions=["target_visible", "target_enabled"],
        expected_effect=expected_effect(expect),
        risk_level="read_only",
    )


def expected_effect(expect: str | None) -> ExpectedEffect:
    if expect:
        return ExpectedEffect(type="content_appears", value=expect)
    return ExpectedEffect(type="none")


def as_url(value: str) -> str:
    if value.startswith(("http://", "https://", "file://")):
        return value
    return Path(value).resolve().as_uri()


def raw_input(
    url: str,
    click: str | None,
    expect: str | None,
    query: str | None = None,
) -> str:
    parts = [f"Open {url}"]
    if click:
        parts.append(f"click {click}")
    if expect:
        parts.append(f"expect {expect}")
    if query:
        parts.append(f"query {query}")
    return "; ".join(parts)


def llm_config_path(
    planner: str,
    value: str | Path | None,
    reviewer: str = "deterministic",
) -> Path | None:
    if planner != "real_llm" and reviewer != "real_llm":
        return None
    if value:
        return Path(value)
    default_path = Path("configs/llm.local.toml")
    return default_path if default_path.exists() else None
