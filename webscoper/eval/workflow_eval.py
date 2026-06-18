from __future__ import annotations

import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from webscoper.api.task_service import TaskService
from webscoper.api.task_state import (
    TaskState,
    status_from_context_state,
    status_from_transcript,
)
from webscoper.runtime.execution.handler import WebAgentExecutionHandler
from webscoper.runtime.prompt.reminders import RuntimeReminderStore
from webscoper.runtime.task_runner import build_task_spec, llm_config_path
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
        failed = total - passed
        summary = WorkflowEvalSummary(
            total=total,
            passed=passed,
            failed=failed,
            pass_rate=passed / total if total else 0.0,
            total_cases=total,
            passed_cases=passed,
            failed_cases=failed,
            recovery_cases_passed=sum(
                1
                for result in results
                if result.case_type == "recovery" and result.passed
            ),
            approval_cases_passed=sum(
                1
                for result in results
                if result.case_type == "approval" and result.passed
            ),
            native_failures=sum(
                1
                for result in results
                if any(diff.startswith("native.") for diff in result.differences)
            ),
            langgraph_failures=sum(
                1
                for result in results
                if any(diff.startswith("langgraph.") for diff in result.differences)
            ),
            comparison_failures=failed,
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
        service = TaskService(runs_dir=self.output_dir / "runs")
        handler: WebAgentExecutionHandler | None = None
        status_override: str | None = None
        error_override: str | None = None

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
                event_sink=_workflow_eval_event_sink(service, run_id, events),
                approval_store=service.approval_store,
                pending_manager=service.pending_manager,
            )
            if backend == "native":
                handler.run_sync(task)
            else:
                _run_langgraph_with_service(service, handler, task, run_id)
            status_override, error_override = _simulate_approval_decision(
                service,
                run_id,
                case.expected.simulate_approval_decision,
            )
            service._write_task_artifacts(run_id)
            return _collect_backend_result(
                backend,
                handler,
                events,
                error=error_override,
                status_override=status_override,
            )
        except Exception as exc:
            if handler is not None:
                if status_override is None:
                    status_override = _service_status(service, run_id)
                return _collect_backend_result(
                    backend,
                    handler,
                    events,
                    error=error_override or f"{type(exc).__name__}: {exc}",
                    status_override=status_override,
                )
            return WorkflowBackendRunResult(
                backend=backend,
                task_id=run_id,
                status="failed",
                error=f"{type(exc).__name__}: {exc}",
                metadata={"event_sink_kinds": events},
            )
        finally:
            try:
                service._write_task_artifacts(run_id)
            except Exception:
                pass


def compare_workflow_backend_results(
    case: WorkflowEvalCase,
    native: WorkflowBackendRunResult,
    langgraph: WorkflowBackendRunResult,
) -> WorkflowComparisonResult:
    differences: list[str] = []
    missing_artifacts: dict[str, list[str]] = {}
    expected = case.expected
    allowed = set(expected.allow_backend_differences)
    expected_status = expected.expected_status or expected.status
    expected_artifacts = sorted(
        set(expected.required_artifacts + expected.expected_artifacts)
    )

    if expected_status is not None:
        for result in (native, langgraph):
            if result.status != expected_status:
                differences.append(
                    f"{result.backend}.status expected {expected_status}, got {result.status}"
                )
    elif native.status != langgraph.status and "status" not in allowed:
        differences.append(
            f"status differs: native={native.status}, langgraph={langgraph.status}"
        )

    for result in (native, langgraph):
        missing = [
            artifact
            for artifact in expected_artifacts
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
            for kind in sorted(
                set(expected.expected_event_kinds + expected.expected_approval_events)
            )
            if kind not in set(result.event_kinds)
        ]
        if missing_events:
            differences.append(
                f"{result.backend}.event_kinds missing: {', '.join(missing_events)}"
            )

    for result in (native, langgraph):
        missing_recovery = [
            kind
            for kind in expected.expected_recovery_kinds
            if kind not in set(result.recovery_kinds)
        ]
        if missing_recovery:
            differences.append(
                f"{result.backend}.recovery_kinds missing: {', '.join(missing_recovery)}"
            )

    if expected.expected_recovery_error_type is not None:
        for result in (native, langgraph):
            if expected.expected_recovery_error_type not in set(result.recovery_error_types):
                differences.append(
                    f"{result.backend}.recovery_error_types expected "
                    f"{expected.expected_recovery_error_type}, got "
                    f"{', '.join(result.recovery_error_types) or None}"
                )

    expected_risk_status = expected.expected_risk_decision or expected.expected_risk_status
    if expected_risk_status is not None:
        for result in (native, langgraph):
            risk_status = result.metadata.get("risk_status")
            if risk_status != expected_risk_status:
                differences.append(
                    f"{result.backend}.risk_status expected "
                    f"{expected_risk_status}, got {risk_status}"
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

    if _unexpected_error(native, expected_status) and "native.error" not in allowed:
        differences.append(f"native.error: {native.error}")
    if _unexpected_error(langgraph, expected_status) and "langgraph.error" not in allowed:
        differences.append(f"langgraph.error: {langgraph.error}")

    differences = [
        difference
        for difference in differences
        if not _allowed_difference(difference, allowed)
    ]
    passed = not differences and not missing_artifacts
    return WorkflowComparisonResult(
        case_id=case.case_id,
        case_type=case.case_type,
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
    status_override: str | None = None,
) -> WorkflowBackendRunResult:
    context = handler.last_context
    run_dir = context.run_dir if context is not None else None
    artifacts = _list_artifacts(run_dir)
    transcript_events = _read_transcript_event_kinds(run_dir)
    stored_events = _read_events_jsonl_kinds(run_dir)
    review_passed, review_score = _read_review(run_dir)
    status, transcript_error = _status_for_run(context, run_dir)
    if status_override is not None:
        status = status_override
    risk_status = _read_risk_status(run_dir)
    recovery_kinds, recovery_error_types = _read_recovery_summary(run_dir)
    approval_statuses = _read_approval_statuses(run_dir)
    return WorkflowBackendRunResult(
        backend=backend,
        task_id=context.run_id if context is not None else None,
        status=status,
        run_dir=str(run_dir) if run_dir is not None else None,
        artifacts=artifacts,
        review_passed=review_passed,
        review_score=review_score,
        event_kinds=sorted(set(transcript_events + stored_events + event_sink_kinds)),
        recovery_kinds=recovery_kinds,
        recovery_error_types=recovery_error_types,
        approval_statuses=approval_statuses,
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
            "pending_count": _jsonl_count(run_dir / "pending.jsonl")
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


def _read_recovery_summary(run_dir: Path | None) -> tuple[list[str], list[str]]:
    if run_dir is None:
        return [], []
    attempts = _read_jsonl_objects(run_dir / "recovery.jsonl")
    kinds = sorted(
        {
            str(attempt.get("strategy"))
            for attempt in attempts
            if attempt.get("strategy") is not None
        }
    )
    error_types = sorted(
        {
            str(attempt.get("error_type"))
            for attempt in attempts
            if attempt.get("error_type") is not None
        }
    )
    return kinds, error_types


def _read_approval_statuses(run_dir: Path | None) -> list[str]:
    if run_dir is None:
        return []
    approvals = _read_jsonl_objects(run_dir / "approvals.jsonl")
    return sorted(
        {
            str(approval.get("status"))
            for approval in approvals
            if approval.get("status") is not None
        }
    )


def _read_jsonl_objects(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            rows.append(payload)
    return rows


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


def _workflow_eval_event_sink(
    service: TaskService,
    run_id: str,
    events: list[str],
):
    def sink(kind: str, message: str, payload: dict[str, Any] | None = None) -> None:
        events.append(kind)
        service._publish_task_event(run_id, kind, message, payload or {})

    return sink


def _run_langgraph_with_service(
    service: TaskService,
    handler: WebAgentExecutionHandler,
    task: Any,
    run_id: str,
):
    service._task_states[run_id] = TaskState(
        task_id=run_id,
        status="running",
        run_dir=service._run_dir(run_id),
        workflow="langgraph",
        thread_id=run_id,
    )
    return service._run_langgraph_workflow(handler, task, run_id)


def _simulate_approval_decision(
    service: TaskService,
    run_id: str,
    decision: str | None,
) -> tuple[str | None, str | None]:
    if decision is None:
        return None, None

    approvals = service.approval_store.list_for_task(run_id)
    if not approvals:
        raise RuntimeError(
            f"Case requested simulated approval decision {decision!r}, "
            "but no approval request was created."
        )

    response = service.decide_approval(
        approvals[-1].approval_id,
        approved=decision == "approved",
        decided_by="workflow_eval",
        reason=f"Workflow eval simulated {decision} decision.",
    )
    service._write_task_artifacts(run_id)
    if response.resume_result is None:
        return _service_status(service, run_id), None
    return response.resume_result.status, response.resume_result.error


def _service_status(service: TaskService, run_id: str) -> str | None:
    status = service.get_task_status(run_id).status
    return None if status == "not_found" else status


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
        f"- Recovery cases passed: {summary.recovery_cases_passed}",
        f"- Approval cases passed: {summary.approval_cases_passed}",
        f"- Native expectation failures: {summary.native_failures}",
        f"- LangGraph expectation failures: {summary.langgraph_failures}",
        f"- Comparison failures: {summary.comparison_failures}",
        "",
        "## Cases",
        "",
        "| Case | Type | Passed | Native Status | LangGraph Status | Differences |",
        "|---|---|---:|---|---|---|",
    ]
    for result in summary.case_results:
        differences = "<br>".join(result.differences) if result.differences else ""
        lines.append(
            "| {case_id} | {case_type} | {passed} | {native_status} | {langgraph_status} | {diffs} |".format(
                case_id=result.case_id,
                case_type=result.case_type,
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
                f"- Missing artifacts: {result.missing_artifacts or {}}",
                f"- Native events: {', '.join(result.native.event_kinds)}",
                f"- LangGraph events: {', '.join(result.langgraph.event_kinds)}",
                f"- Native recovery: {', '.join(result.native.recovery_kinds)}",
                f"- LangGraph recovery: {', '.join(result.langgraph.recovery_kinds)}",
                f"- Native approvals: {', '.join(result.native.approval_statuses)}",
                f"- LangGraph approvals: {', '.join(result.langgraph.approval_statuses)}",
                "",
            ]
        )
    return "\n".join(lines)
