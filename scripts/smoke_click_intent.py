from __future__ import annotations

import argparse
import asyncio
from datetime import UTC, datetime
from pathlib import Path
import sys
from urllib.parse import urlparse

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from webscoper.browser.tool_runtime import StatefulBrowserToolRuntime
from webscoper.browser.public_web import load_public_web_config
from webscoper.runtime.artifacts.trace import TraceRecorder
from webscoper.schemas.browser import ActionContract, ExpectedEffect


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Open a page, click a target by natural-language hint, and verify an effect."
    )
    parser.add_argument("url_or_path", help="Public URL or local HTML file path.")
    parser.add_argument("--click", required=True, help="Natural-language click target hint.")
    parser.add_argument("--expect", required=True, help="Text expected to appear after click.")
    parser.add_argument("--headed", action="store_true", help="Run Chromium in headed mode.")
    parser.add_argument("--public-web-config", help="Optional public web TOML config path.")
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    target_url = _to_url(args.url_or_path)
    run_id = f"run_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}"
    run_dir = Path("traces") / run_id
    recorder = TraceRecorder(run_dir=run_dir, run_id=run_id)
    runtime = StatefulBrowserToolRuntime(
        trace_recorder=recorder,
        headless=not args.headed,
        public_web_config=load_public_web_config(args.public_web_config)
        if args.public_web_config
        else None,
    )
    contract = ActionContract(
        action_type="click",
        intent=f"Click {args.click}",
        target_hint=args.click,
        preferred_roles=["button", "link"],
        preconditions=["target_visible", "target_enabled"],
        expected_effect=ExpectedEffect(
            type="content_appears",
            value=args.expect,
        ),
        risk_level="read_only",
    )

    try:
        await runtime.open_observe(target_url)
        output = await runtime.click_intent(contract)
    finally:
        await runtime.close()

    print(f"run_id: {run_id}")
    observation = output["observation"]
    print(f"final_url: {observation['url']}")
    print(f"title: {observation['title']}")
    print(f"interactive_elements: {len(observation['interactive_elements'])}")
    print(f"risk_signals: {len(observation['risk_signals'])}")
    print(f"trace_path: {recorder.trace_path}")
    if observation.get("screenshot_path"):
        print(f"final_screenshot_path: {observation['screenshot_path']}")


def _to_url(value: str) -> str:
    if urlparse(value).scheme:
        return value
    return Path(value).resolve().as_uri()


if __name__ == "__main__":
    asyncio.run(main())
