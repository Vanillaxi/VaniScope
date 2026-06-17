from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from webscoper.runtime.execution import WebAgentExecutionHandler
from webscoper.runtime.reminders import RuntimeReminderStore
from webscoper.schemas.action import ActionContract, ExpectedEffect
from webscoper.schemas.task import TaskSpec


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a browser task through Agent Harness.")
    parser.add_argument("--url", required=True, help="URL or local file path to open.")
    parser.add_argument("--click", help="Button or link text to click.")
    parser.add_argument("--expect", help="Text expected to appear after the click.")
    parser.add_argument("--workspace", help="Workspace path used for AGENTS.md loading.")
    parser.add_argument(
        "--reminder",
        action="append",
        default=[],
        help="Runtime reminder to inject into the generated prompt. May be repeated.",
    )
    parser.add_argument(
        "--output-root",
        default="runs",
        help="Directory where task run outputs are written.",
    )
    parser.add_argument(
        "--headed",
        action="store_true",
        help="Run browser in headed mode.",
    )
    parser.add_argument(
        "--planner",
        choices=["deterministic", "fake_llm", "real_llm"],
        default="deterministic",
        help="Planner mode to use.",
    )
    parser.add_argument("--model", help="LLM model override for real_llm mode.")
    parser.add_argument(
        "--llm-config",
        help="Path to LLM provider TOML config for real_llm mode.",
    )
    parser.add_argument(
        "--llm-provider",
        help="Provider ID from the LLM config to use for real_llm mode.",
    )
    parser.add_argument(
        "--repair-attempts",
        type=int,
        default=0,
        help="Number of tool-call repair attempts for LLM planner modes.",
    )
    args = parser.parse_args()

    target_url = _as_url(args.url)
    task = TaskSpec(
        task_id="cli_task",
        raw_input=_raw_input(args.url, args.click, args.expect),
        target_url=target_url,
        action=_action(args.click, args.expect) if args.click else None,
        expected_effect=_expected_effect(args.expect) if args.expect else None,
        tags=["cli"],
    )
    reminders = RuntimeReminderStore()
    for reminder in args.reminder:
        reminders.add(reminder, source="cli")

    handler = WebAgentExecutionHandler(
        output_root=Path(args.output_root),
        headless=not args.headed,
        workspace=Path(args.workspace) if args.workspace else None,
        runtime_reminders=reminders,
        planner_mode=args.planner,
        model_override=args.model,
        repair_attempts=args.repair_attempts,
        llm_config_path=_llm_config_path(args.planner, args.llm_config),
        llm_provider=args.llm_provider,
    )
    try:
        observation = asyncio.run(handler.run(task))
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    context = handler.last_context
    prompt_result = handler.last_prompt_result

    print(f"task_id: {task.task_id}")
    print(f"final_url: {observation.url}")
    print(f"title: {observation.title}")
    print(f"planner_mode: {args.planner}")
    if handler.llm_config_path is not None:
        print(f"llm_config_path: {handler.llm_config_path}")
    if args.llm_provider:
        print(f"llm_provider: {args.llm_provider}")
    if handler.version.model != "none":
        print(f"model: {handler.version.model}")
    print(f"repair_attempts: {args.repair_attempts}")
    print("execution_mode: tool_loop")
    print(f"risk_signals_count: {len(observation.risk_signals)}")
    print(f"interactive_elements_count: {len(observation.interactive_elements)}")
    if context is not None:
        print(f"run_dir: {context.run_dir}")
        print(f"trace_path: {context.trace_recorder.trace_path}")
        print(f"transcript_path: {context.transcript_store.transcript_path}")
        print(
            "tool_call_completed_count: "
            f"{_event_count(context.transcript_store.transcript_path, 'tool_call_completed')}"
        )
        print(f"prompt_preview_path: {context.run_dir / 'prompt_preview.md'}")
        print(f"prompt_context_path: {context.run_dir / 'prompt_context.json'}")
    if prompt_result is not None:
        print(f"loaded_agents_md_count: {len(prompt_result.loaded_agents_md_paths)}")

    return 0


def _action(click: str, expect: str | None) -> ActionContract:
    return ActionContract(
        action_type="click",
        intent=f"Click {click}",
        target_hint=click,
        preferred_roles=["button", "link"],
        preconditions=["target_visible", "target_enabled"],
        expected_effect=_expected_effect(expect),
        risk_level="read_only",
    )


def _expected_effect(expect: str | None) -> ExpectedEffect:
    if expect:
        return ExpectedEffect(type="content_appears", value=expect)
    return ExpectedEffect(type="none")


def _as_url(value: str) -> str:
    if value.startswith(("http://", "https://", "file://")):
        return value
    return Path(value).resolve().as_uri()


def _raw_input(url: str, click: str | None, expect: str | None) -> str:
    parts = [f"Open {url}"]
    if click:
        parts.append(f"click {click}")
    if expect:
        parts.append(f"expect {expect}")
    return "; ".join(parts)


def _llm_config_path(planner: str, value: str | None) -> Path | None:
    if planner != "real_llm":
        return None
    if value:
        return Path(value)
    default_path = Path("configs/llm.local.toml")
    return default_path if default_path.exists() else None


def _event_count(transcript_path: Path, event_type: str) -> int:
    if not transcript_path.exists():
        return 0
    count = 0
    for line in transcript_path.read_text(encoding="utf-8").splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("event_type") == event_type:
            count += 1
    return count


if __name__ == "__main__":
    raise SystemExit(main())
