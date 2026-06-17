from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from webscoper.eval.scorer import summarize_results
from webscoper.runtime.browser_runtime import BrowserRuntime
from webscoper.runtime.trace import TraceRecorder
from webscoper.schemas.action import ActionContract, ExpectedEffect
from webscoper.schemas.eval import (
    BrowserEvalCase,
    BrowserEvalCaseResult,
    BrowserEvalSummary,
)
from webscoper.schemas.observation import PageObservation


class BrowserEvalRunner:
    def __init__(
        self,
        cases_path: Path,
        output_root: Path,
        headless: bool = True,
    ) -> None:
        self.cases_path = cases_path
        self.output_root = output_root
        self.headless = headless

    async def run(self) -> BrowserEvalSummary:
        cases = self._load_cases()
        run_id = f"eval_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        run_root = self.output_root / run_id
        run_root.mkdir(parents=True, exist_ok=True)

        results: list[BrowserEvalCaseResult] = []
        for case in cases:
            results.append(await self._run_case(case, run_id, run_root))

        summary = summarize_results(run_id, results)
        self._write_score(run_root, summary)
        self._write_report(run_root, summary)
        return summary

    def _load_cases(self) -> list[BrowserEvalCase]:
        payload = json.loads(self.cases_path.read_text(encoding="utf-8"))
        return [BrowserEvalCase.model_validate(item) for item in payload]

    async def _run_case(
        self,
        case: BrowserEvalCase,
        run_id: str,
        run_root: Path,
    ) -> BrowserEvalCaseResult:
        case_run_dir = run_root / case.case_id
        recorder = TraceRecorder(run_dir=case_run_dir, run_id=f"{run_id}_{case.case_id}")
        runtime = BrowserRuntime(trace_recorder=recorder, headless=self.headless)
        observation: PageObservation | None = None
        fatal_error_type: str | None = None
        fatal_message: str | None = None

        try:
            url = _as_url(case.url)
            if case.click:
                observation = await runtime.open_click_and_observe(
                    url,
                    _action_for_case(case),
                )
            else:
                observation = await runtime.open_and_observe(url)
        except Exception as exc:
            fatal_error_type = type(exc).__name__
            fatal_message = str(exc)

        trace_steps = _read_trace_steps(recorder.trace_path)
        recovery_attempts = _read_jsonl(case_run_dir / "recovery.jsonl")
        evaluation = _evaluate_case(
            case=case,
            observation=observation,
            trace_steps=trace_steps,
            recovery_attempts=recovery_attempts,
            fatal_error_type=fatal_error_type,
            fatal_message=fatal_message,
        )
        recovered = any(
            attempt.get("status") == "succeeded" for attempt in recovery_attempts
        )
        blocked_recovery_count = sum(
            1 for attempt in recovery_attempts if attempt.get("status") == "blocked"
        )

        return BrowserEvalCaseResult(
            case_id=case.case_id,
            passed=evaluation["passed"],
            status=evaluation["status"],
            error_type=evaluation["error_type"],
            message=evaluation["message"],
            run_dir=str(case_run_dir),
            trace_path=str(recorder.trace_path) if recorder.trace_path.exists() else None,
            screenshot_path=_latest_screenshot_path(observation, trace_steps),
            metrics={
                "tags": case.tags,
                "trace_steps": len(trace_steps),
                "recovery_attempt_count": len(recovery_attempts),
                "recovered": recovered,
                "blocked_recovery_count": blocked_recovery_count,
            },
        )

    @staticmethod
    def _write_score(run_root: Path, summary: BrowserEvalSummary) -> None:
        score_path = run_root / "score.json"
        score_path.write_text(
            json.dumps(summary.model_dump(mode="json"), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    @staticmethod
    def _write_report(run_root: Path, summary: BrowserEvalSummary) -> None:
        lines = [
            f"# Browser Eval Report: {summary.run_id}",
            "",
            f"- total_cases: {summary.total_cases}",
            f"- passed_cases: {summary.passed_cases}",
            f"- failed_cases: {summary.failed_cases}",
            f"- task_success_rate: {summary.task_success_rate:.4f}",
            f"- recovery_attempt_count: {summary.recovery_attempt_count}",
            f"- recovered_case_count: {summary.recovered_case_count}",
            f"- recovery_success_rate: {summary.recovery_success_rate:.4f}",
            f"- blocked_recovery_count: {summary.blocked_recovery_count}",
            "",
            "| case_id | passed | status | error_type | trace_path |",
            "| --- | --- | --- | --- | --- |",
        ]
        for result in summary.results:
            lines.append(
                "| {case_id} | {passed} | {status} | {error_type} | {trace_path} |".format(
                    case_id=result.case_id,
                    passed="yes" if result.passed else "no",
                    status=result.status,
                    error_type=result.error_type or "",
                    trace_path=result.trace_path or "",
                )
            )
        lines.append("")
        (run_root / "report.md").write_text("\n".join(lines), encoding="utf-8")


def _action_for_case(case: BrowserEvalCase) -> ActionContract:
    effect = ExpectedEffect(type="none")
    if case.expect.must_contain_text:
        effect = ExpectedEffect(
            type="content_appears",
            value=case.expect.must_contain_text,
        )
    return ActionContract(
        action_type="click",
        intent=f"Click {case.click}",
        target_hint=case.click or "",
        preferred_roles=["button", "link"],
        preconditions=["target_visible", "target_enabled"],
        expected_effect=effect,
        risk_level="read_only",
    )


def _as_url(value: str) -> str:
    if value.startswith(("http://", "https://", "file://")):
        return value
    return Path(value).resolve().as_uri()


def _read_trace_steps(trace_path: Path) -> list[dict[str, Any]]:
    return _read_jsonl(trace_path)


def _read_jsonl(trace_path: Path) -> list[dict[str, Any]]:
    if not trace_path.exists():
        return []

    items: list[dict[str, Any]] = []
    for line in trace_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            items.append(payload)
    return items


def _evaluate_case(
    case: BrowserEvalCase,
    observation: PageObservation | None,
    trace_steps: list[dict[str, Any]],
    recovery_attempts: list[dict[str, Any]],
    fatal_error_type: str | None,
    fatal_message: str | None,
) -> dict[str, Any]:
    failures: list[str] = []
    matched_error_type: str | None = None

    if case.expect.status == "success" and fatal_error_type is not None:
        failures.append(f"Unexpected fatal error: {fatal_error_type}: {fatal_message}")

    if case.expect.must_contain_text:
        text = observation.visible_text_summary if observation else ""
        if case.expect.must_contain_text.lower() not in text.lower():
            failures.append(f"Missing expected text: {case.expect.must_contain_text}")

    if case.expect.must_have_risk_type:
        risk_types = {
            signal.risk_type
            for signal in (observation.risk_signals if observation else [])
        }
        if case.expect.must_have_risk_type not in risk_types:
            failures.append(f"Missing risk type: {case.expect.must_have_risk_type}")

    if case.expect.expected_error_type:
        matched_error_type = _find_error_type(
            trace_steps,
            case.expect.expected_error_type,
        )
        if matched_error_type is None:
            failures.append(f"Missing error type: {case.expect.expected_error_type}")

    unexpected_action_error = _unexpected_action_error(
        case,
        trace_steps,
        recovery_attempts,
    )
    if unexpected_action_error:
        failures.append(f"Unexpected action error: {unexpected_action_error}")
        matched_error_type = matched_error_type or unexpected_action_error

    if fatal_error_type:
        matched_error_type = matched_error_type or fatal_error_type

    return {
        "passed": len(failures) == 0,
        "status": case.expect.status if len(failures) == 0 else "failed",
        "error_type": matched_error_type,
        "message": "; ".join(failures) if failures else "Case matched expectations.",
    }


def _find_error_type(
    trace_steps: list[dict[str, Any]],
    expected_error_type: str,
) -> str | None:
    for step in trace_steps:
        if step.get("error_type") == expected_error_type:
            return expected_error_type
        observation = step.get("observation")
        if isinstance(observation, dict) and observation.get("error_type") == expected_error_type:
            return expected_error_type
    return None


def _unexpected_action_error(
    case: BrowserEvalCase,
    trace_steps: list[dict[str, Any]],
    recovery_attempts: list[dict[str, Any]],
) -> str | None:
    expected_error = case.expect.expected_error_type
    recovered = any(
        attempt.get("status") == "succeeded" for attempt in recovery_attempts
    )
    for step in trace_steps:
        if step.get("action_type") != "browser_click_intent":
            continue
        error_type = step.get("error_type")
        if error_type and recovered:
            continue
        if error_type and error_type != expected_error:
            return str(error_type)
    return None


def _latest_screenshot_path(
    observation: PageObservation | None,
    trace_steps: list[dict[str, Any]],
) -> str | None:
    if observation and observation.screenshot_path:
        return observation.screenshot_path
    for step in reversed(trace_steps):
        screenshot_path = step.get("screenshot_path")
        if screenshot_path:
            return str(screenshot_path)
    return None
