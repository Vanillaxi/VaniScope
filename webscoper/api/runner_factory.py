from __future__ import annotations

from pathlib import Path

from webscoper.api.schemas import TaskCreateRequest
from webscoper.browser.public_web import load_public_web_config
from webscoper.runtime.execution.handler import WebAgentExecutionHandler
from webscoper.runtime.prompt.reminders import RuntimeReminderStore
from webscoper.runtime.execution.runner import build_task_spec, llm_config_path
from webscoper.schemas.task import TaskSpec


def build_handler(service, task_id: str, request: TaskCreateRequest) -> WebAgentExecutionHandler:
    reminders = RuntimeReminderStore()
    if request.reminder:
        reminders.add(request.reminder, source="api")

    return WebAgentExecutionHandler(
        output_root=service.runs_dir,
        workspace=Path(request.workspace) if request.workspace else None,
        runtime_reminders=reminders,
        planner_mode=request.planner,
        model_override=request.model,
        repair_attempts=request.repair_attempts,
        reviewer_mode=request.reviewer,
        revise_attempts=request.revise_attempts,
        llm_config_path=llm_config_path(
            request.planner,
            request.llm_config,
            reviewer=request.reviewer,
        ),
        llm_provider=request.llm_provider,
        run_id_override=task_id,
        event_sink=service._make_event_sink(task_id),
        approval_store=service.approval_store,
        pending_manager=service.pending_manager,
        dry_run=request.dry_run,
        public_web_config=load_public_web_config(request.public_web_config)
        if request.public_web_config
        else service.web_config,
    )


def build_api_task(task_id: str, request: TaskCreateRequest) -> TaskSpec:
    return build_task_spec(
        url=request.url,
        click=request.click,
        expect=request.expect,
        task_type=request.task_type or "browser_task",
        skill_id=request.skill_id,
        query=request.query,
        research_goal=request.research_goal,
        expected_output=request.expect,
        language=request.language,
        task_id=task_id,
    )
