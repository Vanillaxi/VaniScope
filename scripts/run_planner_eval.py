from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from webscoper.eval.planner_eval import PlannerEvalRunner


def main() -> int:
    parser = argparse.ArgumentParser(description="Run LLM planner eval cases.")
    parser.add_argument(
        "--cases",
        default="tests/fixtures/planner_eval_cases.json",
        help="Path to planner eval cases JSON.",
    )
    parser.add_argument(
        "--output-root",
        default="eval_results",
        help="Directory where eval run outputs are written.",
    )
    args = parser.parse_args()

    summary = asyncio.run(
        PlannerEvalRunner(
            cases_path=Path(args.cases),
            output_root=Path(args.output_root),
        ).run()
    )

    run_dir = Path(args.output_root) / summary.run_id
    print(f"run_id: {summary.run_id}")
    print(f"total_cases: {summary.total_cases}")
    print(f"passed_cases: {summary.passed_cases}")
    print(f"failed_cases: {summary.failed_cases}")
    print(f"success_rate: {summary.success_rate:.4f}")
    print(f"parse_success_cases: {summary.parse_success_cases}")
    print(f"validation_success_cases: {summary.validation_success_cases}")
    print(f"repair_used_cases: {summary.repair_used_cases}")
    print(f"score.json: {run_dir / 'score.json'}")
    print(f"report.md: {run_dir / 'report.md'}")

    return 1 if summary.failed_cases > 0 else 0


if __name__ == "__main__":
    raise SystemExit(main())
