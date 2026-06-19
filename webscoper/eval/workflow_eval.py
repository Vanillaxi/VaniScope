from __future__ import annotations

import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from webscoper.api.task_service import TaskService
from webscoper.api.task_state import TaskState, status_from_context_state, status_from_transcript
from webscoper.runtime.execution.handler import WebAgentExecutionHandler
from webscoper.runtime.llm.client import BaseLLMClient
from webscoper.runtime.prompt.reminders import RuntimeReminderStore
from webscoper.runtime.execution.runner import build_task_spec, llm_config_path
from webscoper.schemas.eval import (
    WorkflowEvalCase,
    WorkflowEvalCaseResult,
    WorkflowEvalRunResult,
    WorkflowEvalSummary,
)
from webscoper.schemas.llm import LLMRequest, LLMResponse


class WorkflowRegressionEvalRunner:
    """Run LangGraph-only workflow eval cases.

    The class name is stable for scripts and tests; this runner uses only the
    LangGraph workflow.
    """

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
            langgraph_failures=failed,
            expectation_failures=failed,
            case_results=results,
            metadata={
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "output_dir": str(self.output_dir),
                "backend": "langgraph",
            },
        )
        write_workflow_eval_outputs(summary, self.output_dir)
        return summary

    def run_case(self, case: WorkflowEvalCase) -> WorkflowEvalCaseResult:
        result = self._run_langgraph_case(case)
        return evaluate_workflow_result(case, result)

    def _run_langgraph_case(self, case: WorkflowEvalCase) -> WorkflowEvalRunResult:
        run_id = _safe_run_id(case.case_id)
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
                task_type=case.request.task_type,
                skill_id=case.request.skill_id,
                query=case.request.query,
                research_goal=case.request.research_goal,
                language=case.request.language,
                task_id=run_id,
            )
            reminders = RuntimeReminderStore()
            if case.request.reminder:
                reminders.add(case.request.reminder, source="workflow_eval")
            planner_mode = "fake_llm" if case.request.tool_calls else case.request.planner
            handler = WebAgentExecutionHandler(
                output_root=self.output_dir / "runs",
                headless=True,
                workspace=Path(case.request.workspace) if case.request.workspace else None,
                runtime_reminders=reminders,
                planner_mode=planner_mode,
                repair_attempts=case.request.repair_attempts,
                reviewer_mode=case.request.reviewer,
                revise_attempts=case.request.revise_attempts,
                llm_client=_StaticToolCallsLLMClient(case.request.tool_calls)
                if case.request.tool_calls
                else None,
                llm_config_path=llm_config_path(
                    planner_mode,
                    None,
                    reviewer=case.request.reviewer,
                ),
                run_id_override=run_id,
                event_sink=_workflow_eval_event_sink(service, run_id, events),
                approval_store=service.approval_store,
                pending_manager=service.pending_manager,
            )
            _run_langgraph_with_service(service, handler, task, run_id)
            status_override, error_override = _simulate_approval_decision(
                service,
                run_id,
                case.expected.simulate_approval_decision,
            )
            service._write_task_artifacts(run_id)
            return _collect_result(
                handler,
                events,
                error=error_override,
                status_override=status_override,
            )
        except Exception as exc:
            if handler is not None:
                if status_override is None:
                    status_override = _service_status(service, run_id)
                return _collect_result(
                    handler,
                    events,
                    error=error_override or f"{type(exc).__name__}: {exc}",
                    status_override=status_override,
                )
            return WorkflowEvalRunResult(
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


def evaluate_workflow_result(
    case: WorkflowEvalCase,
    result: WorkflowEvalRunResult,
) -> WorkflowEvalCaseResult:
    differences: list[str] = []
    expected = case.expected
    expected_status = expected.expected_status or expected.status
    expected_artifacts = sorted(
        set(expected.required_artifacts + expected.expected_artifacts)
    )

    if expected_status is not None and result.status != expected_status:
        differences.append(
            f"langgraph.status expected {expected_status}, got {result.status}"
        )

    missing_artifacts = [
        artifact
        for artifact in expected_artifacts
        if artifact not in set(result.artifacts)
    ]
    if missing_artifacts:
        differences.append(
            "langgraph.artifacts missing: " + ", ".join(missing_artifacts)
        )

    if expected.review_passed is not None and result.review_passed != expected.review_passed:
        differences.append(
            f"langgraph.review_passed expected "
            f"{expected.review_passed}, got {result.review_passed}"
        )

    if expected.min_review_score is not None:
        score = result.review_score
        if score is None or score < expected.min_review_score:
            differences.append(
                f"langgraph.review_score expected >= "
                f"{expected.min_review_score}, got {score}"
            )

    for phrase in expected.final_report_contains:
        report_text = str(result.metadata.get("final_report_text") or "")
        if phrase not in report_text:
            differences.append(
                f"langgraph.final_report expected to contain {phrase!r}"
            )

    if expected.min_evidence_count is not None:
        evidence_count = result.metadata.get("evidence_count")
        if not isinstance(evidence_count, int) or evidence_count < expected.min_evidence_count:
            differences.append(
                f"langgraph.evidence_count expected >= "
                f"{expected.min_evidence_count}, got {evidence_count}"
            )

    if expected.skill_status is not None:
        skill_result = result.metadata.get("skill_result")
        actual = skill_result.get("status") if isinstance(skill_result, dict) else None
        if actual != expected.skill_status:
            differences.append(
                f"langgraph.skill_status expected {expected.skill_status}, got {actual}"
            )

    if expected.expected_skill_id is not None:
        skill_result = result.metadata.get("skill_result")
        actual = skill_result.get("skill_id") if isinstance(skill_result, dict) else None
        if actual != expected.expected_skill_id:
            differences.append(
                f"langgraph.skill_id expected {expected.expected_skill_id}, got {actual}"
            )

    if expected.require_affected_modules:
        skill_result = result.metadata.get("skill_result")
        modules = (
            skill_result.get("affected_modules")
            if isinstance(skill_result, dict)
            else None
        )
        if not isinstance(modules, list) or not modules:
            differences.append("langgraph.skill_result affected_modules is empty")

    if expected.require_difficulty:
        skill_result = result.metadata.get("skill_result")
        difficulty = (
            skill_result.get("difficulty") if isinstance(skill_result, dict) else None
        )
        if difficulty not in {"low", "medium", "high"}:
            differences.append(
                f"langgraph.skill_result difficulty missing or invalid: {difficulty}"
            )

    if expected.require_contribution_value:
        skill_result = result.metadata.get("skill_result")
        value = (
            skill_result.get("contribution_value")
            if isinstance(skill_result, dict)
            else None
        )
        if value not in {"low", "medium", "high"}:
            differences.append(
                "langgraph.skill_result contribution_value missing or invalid: "
                f"{value}"
            )

    missing_events = [
        kind
        for kind in sorted(
            set(expected.expected_event_kinds + expected.expected_approval_events)
        )
        if kind not in set(result.event_kinds)
    ]
    if missing_events:
        differences.append(
            f"langgraph.event_kinds missing: {', '.join(missing_events)}"
        )

    missing_recovery = [
        kind
        for kind in expected.expected_recovery_kinds
        if kind not in set(result.recovery_kinds)
    ]
    if missing_recovery:
        differences.append(
            f"langgraph.recovery_kinds missing: {', '.join(missing_recovery)}"
        )

    if expected.expected_recovery_error_type is not None:
        if expected.expected_recovery_error_type not in set(result.recovery_error_types):
            differences.append(
                f"langgraph.recovery_error_types expected "
                f"{expected.expected_recovery_error_type}, got "
                f"{', '.join(result.recovery_error_types) or None}"
            )

    expected_risk_status = expected.expected_risk_decision or expected.expected_risk_status
    if expected_risk_status is not None:
        risk_status = result.metadata.get("risk_status")
        if risk_status != expected_risk_status:
            differences.append(
                f"langgraph.risk_status expected {expected_risk_status}, got {risk_status}"
            )

    if _unexpected_error(result, expected_status):
        differences.append(f"langgraph.error: {result.error}")

    passed = not differences and not missing_artifacts
    return WorkflowEvalCaseResult(
        case_id=case.case_id,
        case_type=case.case_type,
        passed=passed,
        result=result,
        differences=differences,
        missing_artifacts=missing_artifacts,
        summary="LangGraph matched expectations." if passed else "; ".join(differences),
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


def _collect_result(
    handler: WebAgentExecutionHandler,
    event_sink_kinds: list[str],
    error: str | None = None,
    status_override: str | None = None,
) -> WorkflowEvalRunResult:
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
    skill_result = _read_json_object(run_dir / "skill_result.json") if run_dir else None
    final_report_text = _read_text(run_dir / "final_report.md") if run_dir else ""
    return WorkflowEvalRunResult(
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
            "skill_result": skill_result or {},
            "final_report_text": final_report_text,
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


class _StaticToolCallsLLMClient(BaseLLMClient):
    def __init__(self, tool_calls: list[dict[str, Any]]) -> None:
        self.tool_calls = tool_calls

    async def generate(self, request: LLMRequest) -> LLMResponse:
        task_id = str(request.metadata.get("task_id") or "task")
        payload = {
            "task_id": task_id,
            "tool_calls": self.tool_calls,
        }
        return LLMResponse(
            content=f"```json\n{json.dumps(payload, indent=2, ensure_ascii=False)}\n```",
            model="workflow-eval-static-tool-calls",
            usage={"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            raw={"client": "_StaticToolCallsLLMClient"},
        )


def _read_json_object(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


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


def _unexpected_error(
    result: WorkflowEvalRunResult,
    expected_status: str | None,
) -> bool:
    if not result.error:
        return False
    if expected_status is not None and result.status == expected_status:
        return False
    return result.status == "failed"


def _report_markdown(summary: WorkflowEvalSummary) -> str:
    lines = [
        "# VaniScope LangGraph Eval Report",
        "",
        "## Summary",
        "",
        f"- Total: {summary.total}",
        f"- Passed: {summary.passed}",
        f"- Failed: {summary.failed}",
        f"- Pass rate: {summary.pass_rate:.4f}",
        f"- Recovery cases passed: {summary.recovery_cases_passed}",
        f"- Approval cases passed: {summary.approval_cases_passed}",
        f"- LangGraph expectation failures: {summary.langgraph_failures}",
        "",
        "## Cases",
        "",
        "| Case | Type | Passed | Status | Differences |",
        "|---|---|---:|---|---|",
    ]
    for result in summary.case_results:
        differences = "<br>".join(result.differences) if result.differences else ""
        lines.append(
            "| {case_id} | {case_type} | {passed} | {status} | {diffs} |".format(
                case_id=result.case_id,
                case_type=result.case_type,
                passed="yes" if result.passed else "no",
                status=result.result.status,
                diffs=differences,
            )
        )
    lines.extend(["", "## Details", ""])
    for result in summary.case_results:
        run = result.result
        lines.extend(
            [
                f"### {result.case_id}",
                "",
                f"- Passed: {'yes' if result.passed else 'no'}",
                f"- Run dir: {run.run_dir or ''}",
                f"- Summary: {result.summary}",
                f"- Missing artifacts: {result.missing_artifacts or []}",
                f"- Events: {', '.join(run.event_kinds)}",
                f"- Recovery: {', '.join(run.recovery_kinds)}",
                f"- Approvals: {', '.join(run.approval_statuses)}",
                "",
            ]
        )
    return "\n".join(lines)
