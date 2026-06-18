from __future__ import annotations

import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from webscoper.api.task_state import status_from_context_state, status_from_transcript
from webscoper.runtime.execution.handler import WebAgentExecutionHandler
from webscoper.runtime.prompt.reminders import RuntimeReminderStore
from webscoper.runtime.task_runner import build_task_spec, llm_config_path, run_langgraph_workflow_sync
from webscoper.schemas.eval import (
    WorkflowBackendRunResult,
    WorkflowComparisonResult,
    WorkflowEvalCase,
    WorkflowEvalSummary,
)
from webscoper.schemas.workflow import WorkflowBackend


class WorkflowRegressionEvalRunner:
    def __init__(self, output_dir: Path) -> None:
        self.output_dir = output_dir

    def run_file(self, cases_path: Path) -> WorkflowEvalSummary:
        payload = json.loads(cases_path.read_text(encoding="utf-8"))
        cases = [WorkflowEvalCase.model_validate(item) for item in payload]
        return self.run_cases(cases)

    def run_cases(self, cases: list[WorkflowEvalCase]) -> WorkflowEvalSummary:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        results = [self.run_case(case) for case in cases]
        total = len(results)
        passed = sum(1 for result in results if result.passed)
        summary = WorkflowEvalSummary(
            total=total,
            passed=passed,
            failed=total - passed,
            pass_rate=passed / total if total else 0.0,
            case_results=results,
            metadata={
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "output_dir": str(self.output_dir),
                "backends": ["native", "langgraph"],
            },
        )
        write_workflow_eval_outputs(summary, self.output_dir)
        return summary

    def run_case(self, case: WorkflowEvalCase) -> WorkflowComparisonResult:
        native = self._run_backend(case, "native")
        langgraph = self._run_backend(case, "langgraph")
        return compare_workflow_backend_results(case, native, langgraph)

    def _run_backend(
        self,
        case: WorkflowEvalCase,
        backend: WorkflowBackend,
    ) -> WorkflowBackendRunResult:
        run_id = _safe_run_id(f"{case.case_id}_{backend}")
        run_dir = self.output_dir / "runs" / run_id
        if run_dir.exists():
            shutil.rmtree(run_dir)
        events: list[str] = []
        handler: WebAgentExecutionHandler | None = None

        try:
            _guard_offline_request(case)
            task = build_task_spec(
                url=case.request.url,
                click=case.request.click,
                expect=case.request.expect,
                task_id=run_id,
            )
            reminders = RuntimeReminderStore()
            if case.request.reminder:
                reminders.add(case.request.reminder, source="workflow_eval")
            handler = WebAgentExecutionHandler(
                output_root=self.output_dir / "runs",
                headless=True,
                workspace=Path(case.request.workspace) if case.request.workspace else None,
                runtime_reminders=reminders,
                planner_mode=case.request.planner,
                repair_attempts=case.request.repair_attempts,
                reviewer_mode=case.request.reviewer,
                revise_attempts=case.request.revise_attempts,
                llm_config_path=llm_config_path(
                    case.request.planner,
                    None,
                    reviewer=case.request.reviewer,
                ),
                run_id_override=run_id,
                event_sink=lambda kind, _message, _payload: events.append(kind),
            )
            if backend == "native":
                handler.run_sync(task)
            else:
                run_langgraph_workflow_sync(handler, task)
            return _collect_backend_result(backend, handler, events)
        except Exception as exc:
            if handler is not None:
                return _collect_backend_result(
                    backend,
                    handler,
                    events,
                    error=f"{type(exc).__name__}: {exc}",
                )
            return WorkflowBackendRunResult(
                backend=backend,
                task_id=run_id,
                status="failed",
                error=f"{type(exc).__name__}: {exc}",
                metadata={"event_sink_kinds": events},
            )


def compare_workflow_backend_results(
    case: WorkflowEvalCase,
    native: WorkflowBackendRunResult,
    langgraph: WorkflowBackendRunResult,
) -> WorkflowComparisonResult:
    differences: list[str] = []
    missing_artifacts: dict[str, list[str]] = {}
    expected = case.expected
    allowed = set(expected.allow_backend_differences)

    if expected.status is not None:
        for result in (native, langgraph):
            if result.status != expected.status:
                differences.append(
                    f"{result.backend}.status expected {expected.status}, got {result.status}"
                )
    elif native.status != langgraph.status and "status" not in allowed:
        differences.append(
            f"status differs: native={native.status}, langgraph={langgraph.status}"
        )

    for result in (native, langgraph):
        missing = [
            artifact
            for artifact in expected.required_artifacts
            if artifact not in set(result.artifacts)
        ]
        if missing:
            missing_artifacts[result.backend] = missing
            differences.append(f"{result.backend}.artifacts missing: {', '.join(missing)}")

    if expected.review_passed is not None:
        for result in (native, langgraph):
            if result.review_passed != expected.review_passed:
                differences.append(
                    f"{result.backend}.review_passed expected "
                    f"{expected.review_passed}, got {result.review_passed}"
                )

    if expected.min_review_score is not None:
        for result in (native, langgraph):
            score = result.review_score
            if score is None or score < expected.min_review_score:
                differences.append(
                    f"{result.backend}.review_score expected >= "
                    f"{expected.min_review_score}, got {score}"
                )
    elif (
        native.review_score is not None
        and langgraph.review_score is not None
        and abs(native.review_score - langgraph.review_score) > 0.0001
        and "review_score" not in allowed
    ):
        differences.append(
            "review_score differs: "
            f"native={native.review_score}, langgraph={langgraph.review_score}"
        )

    if (
        expected.review_passed is None
        and native.review_passed is not None
        and langgraph.review_passed is not None
        and native.review_passed != langgraph.review_passed
        and "review_passed" not in allowed
    ):
        differences.append(
            "review_passed differs: "
            f"native={native.review_passed}, langgraph={langgraph.review_passed}"
        )

    for result in (native, langgraph):
        missing_events = [
            kind
            for kind in expected.expected_event_kinds
            if kind not in set(result.event_kinds)
        ]
        if missing_events:
            differences.append(
                f"{result.backend}.event_kinds missing: {', '.join(missing_events)}"
            )

    if expected.expected_risk_status is not None:
        for result in (native, langgraph):
            risk_status = result.metadata.get("risk_status")
            if risk_status != expected.expected_risk_status:
                differences.append(
                    f"{result.backend}.risk_status expected "
                    f"{expected.expected_risk_status}, got {risk_status}"
                )

    for metadata_key in (
        "evidence_count",
        "recovery_attempt_count",
        "approval_request_count",
    ):
        if metadata_key in allowed:
            continue
        native_value = native.metadata.get(metadata_key)
        langgraph_value = langgraph.metadata.get(metadata_key)
        if native_value != langgraph_value:
            differences.append(
                f"{metadata_key} differs: "
                f"native={native_value}, langgraph={langgraph_value}"
            )

    if _unexpected_error(native, expected.status) and "native.error" not in allowed:
        differences.append(f"native.error: {native.error}")
    if _unexpected_error(langgraph, expected.status) and "langgraph.error" not in allowed:
        differences.append(f"langgraph.error: {langgraph.error}")

    differences = [
        difference
        for difference in differences
        if not _allowed_difference(difference, allowed)
    ]
    passed = not differences and not missing_artifacts
    return WorkflowComparisonResult(
        case_id=case.case_id,
        passed=passed,
        native=native,
        langgraph=langgraph,
        differences=differences,
        missing_artifacts=missing_artifacts,
        summary="Backends matched expectations." if passed else "; ".join(differences),
    )


def write_workflow_eval_outputs(
    summary: WorkflowEvalSummary,
    output_dir: Path,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "score.json").write_text(
        json.dumps(summary.model_dump(mode="json"), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    (output_dir / "report.md").write_text(
        _report_markdown(summary),
        encoding="utf-8",
    )


def _collect_backend_result(
    backend: str,
    handler: WebAgentExecutionHandler,
    event_sink_kinds: list[str],
    error: str | None = None,
) -> WorkflowBackendRunResult:
    context = handler.last_context
    run_dir = context.run_dir if context is not None else None
    artifacts = _list_artifacts(run_dir)
    transcript_events = _read_transcript_event_kinds(run_dir)
    stored_events = _read_events_jsonl_kinds(run_dir)
    review_passed, review_score = _read_review(run_dir)
    status, transcript_error = _status_for_run(context, run_dir)
    risk_status = _read_risk_status(run_dir)
    return WorkflowBackendRunResult(
        backend=backend,
        task_id=context.run_id if context is not None else None,
        status=status,
        run_dir=str(run_dir) if run_dir is not None else None,
        artifacts=artifacts,
        review_passed=review_passed,
        review_score=review_score,
        event_kinds=sorted(set(transcript_events + stored_events + event_sink_kinds)),
        error=error or transcript_error,
        metadata={
            "risk_status": risk_status,
            "evidence_count": _jsonl_count(run_dir / "evidence.jsonl")
            if run_dir is not None
            else 0,
            "recovery_attempt_count": _jsonl_count(run_dir / "recovery.jsonl")
            if run_dir is not None
            else 0,
            "approval_request_count": _jsonl_count(run_dir / "approvals.jsonl")
            if run_dir is not None
            else 0,
            "event_sink_kinds": sorted(set(event_sink_kinds)),
        },
    )


def _status_for_run(context: Any | None, run_dir: Path | None) -> tuple[str, str | None]:
    if context is not None:
        return status_from_context_state(context.state.status), context.state.error_message
    if run_dir is not None:
        return status_from_transcript(run_dir)
    return "failed", "Missing run context."


def _list_artifacts(run_dir: Path | None) -> list[str]:
    if run_dir is None or not run_dir.exists():
        return []
    return sorted(path.name for path in run_dir.iterdir() if path.is_file())


def _read_review(run_dir: Path | None) -> tuple[bool | None, float | None]:
    payload = _read_json_object(run_dir / "review.json") if run_dir is not None else None
    if payload is None:
        return None, None
    passed = payload.get("passed")
    score = payload.get("score")
    return (
        passed if isinstance(passed, bool) else None,
        float(score) if isinstance(score, (int, float)) else None,
    )


def _read_transcript_event_kinds(run_dir: Path | None) -> list[str]:
    if run_dir is None:
        return []
    transcript_path = run_dir / "transcript.jsonl"
    if not transcript_path.exists():
        return []
    kinds: list[str] = []
    for line in transcript_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        kind = payload.get("event_type")
        if isinstance(kind, str):
            kinds.append(kind)
    return kinds


def _read_events_jsonl_kinds(run_dir: Path | None) -> list[str]:
    if run_dir is None:
        return []
    events_path = run_dir / "events.jsonl"
    if not events_path.exists():
        return []
    kinds: list[str] = []
    for line in events_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        kind = payload.get("kind") or payload.get("event")
        if isinstance(kind, str):
            kinds.append(kind)
    return kinds


def _jsonl_count(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())


def _read_risk_status(run_dir: Path | None) -> str | None:
    payload = _read_json_object(run_dir / "risk_report.json") if run_dir is not None else None
    if payload is None:
        return None
    if int(payload.get("blocked") or 0) > 0:
        return "blocked"
    if int(payload.get("approval_required") or 0) > 0:
        return "requires_approval"
    return "allowed"


def _read_json_object(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _guard_offline_request(case: WorkflowEvalCase) -> None:
    url = case.request.url
    if url.startswith(("http://", "https://")):
        raise ValueError(
            f"Workflow eval cases must use local fixture URLs, got {url!r}."
        )
    if case.request.planner == "real_llm" or case.request.reviewer == "real_llm":
        raise ValueError("Workflow eval must not use real_llm planner or reviewer.")


def _safe_run_id(value: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("._")
    return safe or "workflow_eval_case"


def _allowed_difference(difference: str, allowed: set[str]) -> bool:
    return any(token and token in difference for token in allowed)


def _unexpected_error(
    result: WorkflowBackendRunResult,
    expected_status: str | None,
) -> bool:
    if not result.error:
        return False
    if expected_status is not None and result.status == expected_status:
        return False
    return result.status == "failed"


def _report_markdown(summary: WorkflowEvalSummary) -> str:
    lines = [
        "# VaniScope Workflow Regression Eval Report",
        "",
        "## Summary",
        "",
        f"- Total: {summary.total}",
        f"- Passed: {summary.passed}",
        f"- Failed: {summary.failed}",
        f"- Pass rate: {summary.pass_rate:.4f}",
        "",
        "## Cases",
        "",
        "| Case | Passed | Native Status | LangGraph Status | Differences |",
        "|---|---:|---|---|---|",
    ]
    for result in summary.case_results:
        differences = "<br>".join(result.differences) if result.differences else ""
        lines.append(
            "| {case_id} | {passed} | {native_status} | {langgraph_status} | {diffs} |".format(
                case_id=result.case_id,
                passed="yes" if result.passed else "no",
                native_status=result.native.status,
                langgraph_status=result.langgraph.status,
                diffs=differences,
            )
        )
    lines.extend(["", "## Details", ""])
    for result in summary.case_results:
        lines.extend(
            [
                f"### {result.case_id}",
                "",
                f"- Passed: {'yes' if result.passed else 'no'}",
                f"- Native run dir: {result.native.run_dir or ''}",
                f"- LangGraph run dir: {result.langgraph.run_dir or ''}",
                f"- Summary: {result.summary}",
                "",
            ]
        )
    return "\n".join(lines)
