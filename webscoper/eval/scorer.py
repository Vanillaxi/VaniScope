from __future__ import annotations

from webscoper.schemas.eval import BrowserEvalCaseResult, BrowserEvalSummary


def compute_task_success_rate(total: int, passed: int) -> float:
    if total == 0:
        return 0.0
    return passed / total


def summarize_results(
    run_id: str,
    results: list[BrowserEvalCaseResult],
) -> BrowserEvalSummary:
    total = len(results)
    passed = sum(1 for result in results if result.passed)
    return BrowserEvalSummary(
        run_id=run_id,
        total_cases=total,
        passed_cases=passed,
        failed_cases=total - passed,
        task_success_rate=compute_task_success_rate(total, passed),
        results=results,
    )
