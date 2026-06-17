from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from webscoper.eval.reviewer_eval import (
    ReviewerEvalRunner,
    write_reviewer_eval_outputs,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run reviewer eval cases.")
    parser.add_argument(
        "--cases",
        default="tests/fixtures/reviewer_eval_cases.json",
        help="Path to reviewer eval cases JSON.",
    )
    parser.add_argument(
        "--output-dir",
        help="Directory where score.json and report.md are written.",
    )
    args = parser.parse_args()

    output_dir = (
        Path(args.output_dir)
        if args.output_dir
        else Path("eval_results") / f"reviewer_eval_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    )
    summary = ReviewerEvalRunner().run_file(Path(args.cases))
    write_reviewer_eval_outputs(summary, output_dir)

    print(f"total: {summary.total}")
    print(f"passed: {summary.passed}")
    print(f"failed: {summary.failed}")
    print(f"pass_rate: {summary.pass_rate:.4f}")
    print(f"average_review_score: {summary.average_review_score:.4f}")
    print(f"score.json: {output_dir / 'score.json'}")
    print(f"report.md: {output_dir / 'report.md'}")

    return 1 if summary.failed > 0 else 0


if __name__ == "__main__":
    raise SystemExit(main())
