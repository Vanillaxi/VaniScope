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
    recovery_attempt_count = sum(
        int(result.metrics.get("recovery_attempt_count", 0))
        for result in results
    )
    recovered_case_count = sum(
        1 for result in results if bool(result.metrics.get("recovered", False))
    )
    recovery_case_count = sum(
        1
        for result in results
        if int(result.metrics.get("recovery_attempt_count", 0)) > 0
    )
    blocked_recovery_count = sum(
        int(result.metrics.get("blocked_recovery_count", 0))
        for result in results
    )
    return BrowserEvalSummary(
        run_id=run_id,
        total_cases=total,
        passed_cases=passed,
        failed_cases=total - passed,
        task_success_rate=compute_task_success_rate(total, passed),
        recovery_attempt_count=recovery_attempt_count,
        recovered_case_count=recovered_case_count,
        recovery_success_rate=compute_task_success_rate(
            recovery_case_count,
            recovered_case_count,
        ),
        blocked_recovery_count=blocked_recovery_count,
        results=results,
    )
