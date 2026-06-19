from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from webscoper.runtime.task_runner import run_browser_task_sync


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
    parser.add_argument(
        "--reviewer",
        choices=["deterministic", "fake_llm", "real_llm"],
        default="deterministic",
        help="Reviewer mode to use for optional revise loop.",
    )
    parser.add_argument(
        "--revise-attempts",
        type=int,
        default=0,
        help="Number of reviewer revise attempts to run after final report generation.",
    )
    args = parser.parse_args()

    try:
        result = run_browser_task_sync(
            url=args.url,
            click=args.click,
            expect=args.expect,
            planner=args.planner,
            output_root=Path(args.output_root),
            headed=args.headed,
            workspace=Path(args.workspace) if args.workspace else None,
            reminders=args.reminder,
            model_override=args.model,
            repair_attempts=args.repair_attempts,
            reviewer=args.reviewer,
            revise_attempts=args.revise_attempts,
            llm_config=args.llm_config,
            llm_provider=args.llm_provider,
            reminder_source="cli",
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    task = result.task
    observation = result.observation
    handler = result.handler
    context = handler.last_context
    prompt_result = handler.last_prompt_result

    print(f"task_id: {task.task_id}")
    print(f"final_url: {observation.url}")
    print(f"title: {observation.title}")
    print(f"planner_mode: {args.planner}")
    print("workflow_backend: langgraph")
    if handler.llm_config_path is not None:
        print(f"llm_config_path: {handler.llm_config_path}")
    if args.llm_provider:
        print(f"llm_provider: {args.llm_provider}")
    if handler.version.model != "none":
        print(f"model: {handler.version.model}")
    print(f"repair_attempts: {args.repair_attempts}")
    print(f"reviewer_mode: {args.reviewer}")
    print(f"revise_attempts: {args.revise_attempts}")
    print("execution_mode: tool_loop")
    print(f"risk_signals_count: {len(observation.risk_signals)}")
    print(f"interactive_elements_count: {len(observation.interactive_elements)}")
    if context is not None:
        print(f"run_dir: {context.run_dir}")
        print(f"trace_path: {context.trace_recorder.trace_path}")
        print(f"transcript_path: {context.transcript_store.transcript_path}")
        print(f"evidence_path: {context.run_dir / 'evidence.jsonl'}")
        print(f"final_report_path: {context.run_dir / 'final_report.md'}")
        print(f"review_path: {context.run_dir / 'review.json'}")
        print(f"review_summary_path: {context.run_dir / 'review_summary.md'}")
        if (context.run_dir / "revise_loop.json").exists():
            print(f"revision_plan_path: {context.run_dir / 'revision_plan.json'}")
            print(f"revised_report_path: {context.run_dir / 'revised_report.md'}")
            print(f"final_review_path: {context.run_dir / 'final_review.json'}")
            print(f"revise_loop_path: {context.run_dir / 'revise_loop.json'}")
        print(
            "tool_call_completed_count: "
            f"{_event_count(context.transcript_store.transcript_path, 'tool_call_completed')}"
        )
        print(f"prompt_preview_path: {context.run_dir / 'prompt_preview.md'}")
        print(f"prompt_context_path: {context.run_dir / 'prompt_context.json'}")
        if (context.run_dir / "workflow_state.json").exists():
            print(f"workflow_state_path: {context.run_dir / 'workflow_state.json'}")
    if prompt_result is not None:
        print(f"loaded_agents_md_count: {len(prompt_result.loaded_agents_md_paths)}")

    return 0


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
