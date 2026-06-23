from __future__ import annotations

from pathlib import Path
from typing import Any

from webscoper.api.schemas import TaskCreateRequest
from webscoper.browser.public_web import load_public_web_config
from webscoper.runtime.execution.handler import WebAgentExecutionHandler
from webscoper.runtime.execution.planner import normalize_planner_mode
from webscoper.runtime.localization import select_task_languages
from webscoper.runtime.prompt.builder import RuntimeReminderStore
from webscoper.runtime.execution.runner import build_task_spec, llm_config_path
from webscoper.runtime.llm.config import (
    load_llm_router_config_from_file,
    resolve_llm_provider_config,
)
from webscoper.schemas.task import TaskSpec


def build_handler(service, task_id: str, request: TaskCreateRequest) -> WebAgentExecutionHandler:
    reminders = RuntimeReminderStore()
    if request.reminder:
        reminders.add(request.reminder, source="api")
    planner_mode = resolve_request_planner_mode(request)
    config_path = llm_config_path(
        planner_mode,
        request.llm_config,
        reviewer=request.reviewer,
    )
    if planner_mode == "real_llm":
        _require_real_llm_configured(config_path, request)

    return WebAgentExecutionHandler(
        output_root=service.runs_dir,
        workspace=Path(request.workspace) if request.workspace else None,
        runtime_reminders=reminders,
        planner_mode=planner_mode,
        model_override=request.model,
        repair_attempts=request.repair_attempts,
        reviewer_mode=request.reviewer,
        revise_attempts=request.revise_attempts,
        llm_config_path=config_path,
        llm_provider=request.llm_provider,
        run_id_override=task_id,
        event_sink=service._make_event_sink(task_id),
        approval_store=service.approval_store,
        pending_manager=service.pending_manager,
        control_store=service.control_store,
        dry_run=request.dry_run,
        public_web_config=load_public_web_config(request.public_web_config)
        if request.public_web_config
        else service.web_config,
    )


def validate_request_planner_configuration(request: TaskCreateRequest) -> None:
    planner_mode = resolve_request_planner_mode(request)
    config_path = llm_config_path(
        planner_mode,
        request.llm_config,
        reviewer=request.reviewer,
    )
    if planner_mode == "real_llm":
        _require_real_llm_configured(config_path, request)


def build_api_task(task_id: str, request: TaskCreateRequest) -> TaskSpec:
    languages = select_task_languages(
        goal=request.goal,
        query=request.query,
        research_goal=request.research_goal,
        expected_output=request.expect,
        language=request.language,
        display_language=request.display_language,
        preferred_report_language=request.preferred_report_language,
        requested_output_language=request.requested_output_language,
    )
    task = build_task_spec(
        url=request.url,
        click=request.click,
        expect=request.expect,
        task_type=request.task_type or "browser_task",
        mode=request.mode,
        skill_id=request.skill_id,
        goal=request.goal,
        query=request.query,
        research_goal=request.research_goal,
        expected_output=request.expect,
        language=languages.report_language,
        display_language=languages.display_language,
        requested_output_language=languages.requested_output_language,
        preferred_report_language=languages.report_language,
        task_id=task_id,
    )
    if request.max_steps is not None:
        task.budget.max_steps = request.max_steps
    return task


def resolve_request_planner_mode(request: TaskCreateRequest) -> str:
    explicit_planner = _explicit_planner_value(request)
    if request.use_real_llm:
        return "real_llm"
    if explicit_planner is not None:
        return normalize_planner_mode(explicit_planner)
    if _should_auto_select_real_llm(request):
        return "real_llm"
    return normalize_planner_mode(request.planner)


def _explicit_planner_value(request: TaskCreateRequest) -> str | None:
    fields_set = getattr(request, "model_fields_set", set())
    if "planner_mode" in fields_set and request.planner_mode:
        return request.planner_mode
    if "planner" in fields_set and request.planner:
        return request.planner
    return None


def _should_auto_select_real_llm(request: TaskCreateRequest) -> bool:
    task_type = request.task_type or "browser_task"
    if task_type != "browser_task" or request.mode != "auto_explore":
        return False
    config_path = llm_config_path("real_llm", request.llm_config, reviewer=request.reviewer)
    return _real_llm_configured(config_path, request)


def _real_llm_configured(config_path: Path | None, request: TaskCreateRequest) -> bool:
    try:
        _resolve_real_provider(config_path, request)
        return True
    except ValueError:
        return False


def _require_real_llm_configured(
    config_path: Path | None,
    request: TaskCreateRequest,
) -> None:
    try:
        _resolve_real_provider(config_path, request)
    except ValueError as exc:
        raise ValueError(
            "Real LLM requested but default provider is not configured."
        ) from exc


def _resolve_real_provider(config_path: Path | None, request: TaskCreateRequest) -> Any:
    if config_path is None:
        raise ValueError("Missing LLM config file.")
    router = load_llm_router_config_from_file(config_path)
    provider = resolve_llm_provider_config(
        router,
        provider_id=request.llm_provider,
        model_override=request.model,
    )
    if provider.provider_type != "openai_compatible":
        raise ValueError("Default LLM provider is not real.")
    return provider
