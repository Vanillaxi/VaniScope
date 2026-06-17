from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from webscoper.runtime.execution import WebAgentExecutionHandler
from webscoper.runtime.reminders import RuntimeReminderStore
from webscoper.schemas.action import ActionContract, ExpectedEffect
from webscoper.schemas.observation import PageObservation
from webscoper.schemas.task import TaskSpec


@dataclass
class TaskRunOutput:
    task: TaskSpec
    observation: PageObservation
    handler: WebAgentExecutionHandler


def run_browser_task_sync(
    url: str,
    click: str | None = None,
    expect: str | None = None,
    planner: str = "deterministic",
    workspace: str | Path | None = None,
    reminders: list[str] | None = None,
    output_root: Path = Path("runs"),
    headed: bool = False,
    model_override: str | None = None,
    repair_attempts: int = 0,
    llm_config: str | Path | None = None,
    llm_provider: str | None = None,
    task_id: str = "cli_task",
    reminder_source: str = "runtime",
) -> TaskRunOutput:
    task = build_task_spec(
        url=url,
        click=click,
        expect=expect,
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
        llm_config_path=llm_config_path(planner, llm_config),
        llm_provider=llm_provider,
    )
    observation = handler.run_sync(task)
    return TaskRunOutput(task=task, observation=observation, handler=handler)


def build_task_spec(
    url: str,
    click: str | None = None,
    expect: str | None = None,
    task_id: str = "cli_task",
) -> TaskSpec:
    return TaskSpec(
        task_id=task_id,
        raw_input=raw_input(url, click, expect),
        target_url=as_url(url),
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


def raw_input(url: str, click: str | None, expect: str | None) -> str:
    parts = [f"Open {url}"]
    if click:
        parts.append(f"click {click}")
    if expect:
        parts.append(f"expect {expect}")
    return "; ".join(parts)


def llm_config_path(planner: str, value: str | Path | None) -> Path | None:
    if planner != "real_llm":
        return None
    if value:
        return Path(value)
    default_path = Path("configs/llm.local.toml")
    return default_path if default_path.exists() else None
