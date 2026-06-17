from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from webscoper.eval.browser_eval import BrowserEvalRunner


def main() -> int:
    parser = argparse.ArgumentParser(description="Run local Browser Runtime eval cases.")
    parser.add_argument(
        "--cases",
        default="tests/fixtures/eval_cases/browser_runtime_cases.json",
        help="Path to browser eval cases JSON.",
    )
    parser.add_argument(
        "--output-root",
        default="eval_results",
        help="Directory where eval run outputs are written.",
    )
    parser.add_argument(
        "--headed",
        action="store_true",
        help="Run browser in headed mode.",
    )
    args = parser.parse_args()

    summary = asyncio.run(
        BrowserEvalRunner(
            cases_path=Path(args.cases),
            output_root=Path(args.output_root),
            headless=not args.headed,
        ).run()
    )

    run_dir = Path(args.output_root) / summary.run_id
    print(f"run_id: {summary.run_id}")
    print(f"total_cases: {summary.total_cases}")
    print(f"passed_cases: {summary.passed_cases}")
    print(f"failed_cases: {summary.failed_cases}")
    print(f"task_success_rate: {summary.task_success_rate:.4f}")
    print(f"score.json: {run_dir / 'score.json'}")
    print(f"report.md: {run_dir / 'report.md'}")

    return 1 if summary.failed_cases > 0 else 0


if __name__ == "__main__":
    raise SystemExit(main())
