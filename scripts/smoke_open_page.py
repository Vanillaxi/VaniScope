from __future__ import annotations

import argparse
import asyncio
from datetime import UTC, datetime
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from webscoper.runtime.browser_runtime import BrowserRuntime
from webscoper.runtime.trace import TraceRecorder


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Open a public page and write a browser trace.")
    parser.add_argument("url", help="Public URL to open.")
    parser.add_argument("--headed", action="store_true", help="Run Chromium in headed mode.")
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    run_id = f"run_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}"
    run_dir = Path("traces") / run_id
    recorder = TraceRecorder(run_dir=run_dir, run_id=run_id)
    runtime = BrowserRuntime(trace_recorder=recorder, headless=not args.headed)

    observation = await runtime.open_and_observe(args.url)

    print(f"run_id: {run_id}")
    print(f"url: {observation.url}")
    print(f"title: {observation.title}")
    print(f"screenshot_path: {observation.screenshot_path}")
    print(f"interactive_elements: {len(observation.interactive_elements)}")
    print(f"risk_signals: {len(observation.risk_signals)}")
    print(f"trace_path: {recorder.trace_path}")


if __name__ == "__main__":
    asyncio.run(main())
