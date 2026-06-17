from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from webscoper.runtime.execution import WebAgentExecutionHandler
from webscoper.schemas.action import ActionContract, ExpectedEffect
from webscoper.schemas.task import TaskSpec


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a browser task through Agent Harness.")
    parser.add_argument("--url", required=True, help="URL or local file path to open.")
    parser.add_argument("--click", help="Button or link text to click.")
    parser.add_argument("--expect", help="Text expected to appear after the click.")
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
    handler = WebAgentExecutionHandler(
        output_root=Path(args.output_root),
        headless=not args.headed,
    )
    observation = asyncio.run(handler.run(task))
    context = handler.last_context

    print(f"task_id: {task.task_id}")
    print(f"final_url: {observation.url}")
    print(f"title: {observation.title}")
    print(f"risk_signals_count: {len(observation.risk_signals)}")
    print(f"interactive_elements_count: {len(observation.interactive_elements)}")
    if context is not None:
        print(f"run_dir: {context.run_dir}")
        print(f"trace_path: {context.trace_recorder.trace_path}")
        print(f"transcript_path: {context.transcript_store.transcript_path}")

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


if __name__ == "__main__":
    raise SystemExit(main())
