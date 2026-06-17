from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from webscoper.runtime.context import WebAgentContext
from webscoper.runtime.llm_client import BaseLLMClient
from webscoper.runtime.llm_planner import LLMTaskPlanner
from webscoper.runtime.plan_validator import PlanValidator
from webscoper.runtime.trace import TraceRecorder
from webscoper.runtime.transcript import TranscriptStore
from webscoper.schemas.action import ActionContract, ExpectedEffect
from webscoper.schemas.context import RuntimeState
from webscoper.schemas.llm import LLMRequest, LLMResponse
from webscoper.schemas.plan import ExecutionPlan
from webscoper.schemas.plan_validation import PlanValidationResult
from webscoper.schemas.planner_eval import (
    PlannerEvalCase,
    PlannerEvalCaseResult,
    PlannerEvalSummary,
)
from webscoper.schemas.prompt import PromptBuildResult
from webscoper.schemas.task import TaskSpec
from webscoper.schemas.version import VersionContext
from webscoper.tools.registry import create_default_tool_registry


class PlannerEvalRunner:
    def __init__(
        self,
        cases_path: Path,
        output_root: Path = Path("eval_results"),
    ) -> None:
        self.cases_path = cases_path
        self.output_root = output_root

    async def run(self) -> PlannerEvalSummary:
        cases = self._load_cases()
        run_id = f"planner_eval_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        run_root = self.output_root / run_id
        run_root.mkdir(parents=True, exist_ok=True)

        results: list[PlannerEvalCaseResult] = []
        for case in cases:
            results.append(await self._run_case(case, run_id, run_root))

        summary = _summarize(run_id, results)
        self._write_score(run_root, summary)
        self._write_report(run_root, summary)
        return summary

    def _load_cases(self) -> list[PlannerEvalCase]:
        payload = json.loads(self.cases_path.read_text(encoding="utf-8"))
        return [PlannerEvalCase.model_validate(item) for item in payload]

    async def _run_case(
        self,
        case: PlannerEvalCase,
        run_id: str,
        run_root: Path,
    ) -> PlannerEvalCaseResult:
        context = _context_for_case(case, run_id, run_root / case.case_id)
        planner = LLMTaskPlanner(
            ScriptedLLMClient([case.llm_output, case.repair_output]),
            repair_attempts=case.repair_attempts,
        )
        plan: ExecutionPlan | None = None
        validation: PlanValidationResult | None = None
        status = "failed"
        error_type: str | None = None
        message: str | None = None

        try:
            plan = await planner.build_plan(
                context.snapshot(),
                PromptBuildResult(prompt_text="test prompt"),
            )
            validation = PlanValidator(create_default_tool_registry()).validate(
                plan,
                context.snapshot(),
            )
            if validation.ok:
                status = "success"
            else:
                error_type = validation.issues[0].issue_type
                message = validation.issues[0].message
        except RuntimeError as exc:
            error_type = _error_type_from_exception(exc)
            message = str(exc)

        parsed_tool_ids = (
            [step.tool_call.tool_id for step in plan.steps]
            if plan is not None
            else _parsed_tool_ids_from_planner(planner)
        )
        validation_issues = (
            [issue.model_dump(mode="json") for issue in validation.issues]
            if validation is not None
            else []
        )
        passed = _case_passed(
            case=case,
            status=status,
            error_type=error_type,
            parsed_tool_ids=parsed_tool_ids,
        )

        return PlannerEvalCaseResult(
            case_id=case.case_id,
            passed=passed,
            status=status,
            error_type=error_type,
            message=message or ("Case matched expectations." if passed else None),
            parsed_tool_ids=parsed_tool_ids,
            validation_status=validation.status if validation is not None else None,
            validation_issues=validation_issues,
            repair_used=bool(planner.repair_requests),
        )

    @staticmethod
    def _write_score(run_root: Path, summary: PlannerEvalSummary) -> None:
        (run_root / "score.json").write_text(
            json.dumps(summary.model_dump(mode="json"), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    @staticmethod
    def _write_report(run_root: Path, summary: PlannerEvalSummary) -> None:
        lines = [
            f"# Planner Eval Report: {summary.run_id}",
            "",
            f"- total_cases: {summary.total_cases}",
            f"- passed_cases: {summary.passed_cases}",
            f"- failed_cases: {summary.failed_cases}",
            f"- success_rate: {summary.success_rate:.4f}",
            f"- parse_success_cases: {summary.parse_success_cases}",
            f"- validation_success_cases: {summary.validation_success_cases}",
            f"- repair_used_cases: {summary.repair_used_cases}",
            "",
            "| case_id | passed | status | error_type | parsed_tool_ids | validation_status | repair_used |",
            "| --- | --- | --- | --- | --- | --- | --- |",
        ]
        for result in summary.results:
            lines.append(
                "| {case_id} | {passed} | {status} | {error_type} | {tool_ids} | {validation_status} | {repair_used} |".format(
                    case_id=result.case_id,
                    passed="yes" if result.passed else "no",
                    status=result.status,
                    error_type=result.error_type or "",
                    tool_ids=", ".join(result.parsed_tool_ids),
                    validation_status=result.validation_status or "",
                    repair_used="yes" if result.repair_used else "no",
                )
            )
        lines.append("")
        (run_root / "report.md").write_text("\n".join(lines), encoding="utf-8")


class ScriptedLLMClient(BaseLLMClient):
    def __init__(self, outputs: list[str | None]) -> None:
        self.outputs = [output for output in outputs if output is not None]
        self.index = 0

    async def generate(self, request: LLMRequest) -> LLMResponse:
        if self.index >= len(self.outputs):
            output = self.outputs[-1] if self.outputs else ""
        else:
            output = self.outputs[self.index]
        self.index += 1
        return LLMResponse(content=output, model="scripted-llm")


def _context_for_case(
    case: PlannerEvalCase,
    run_id: str,
    run_dir: Path,
) -> WebAgentContext:
    task = TaskSpec(
        task_id=case.case_id,
        raw_input=case.raw_input,
        target_url=_as_url(case.target_url),
        action=_action_for_case(case) if case.click else None,
        expected_effect=_expected_effect(case.expect_text) if case.expect_text else None,
        tags=case.tags,
    )
    return WebAgentContext(
        task=task,
        run_id=f"{run_id}_{case.case_id}",
        run_dir=run_dir,
        trace_recorder=TraceRecorder(run_dir=run_dir, run_id=run_id),
        transcript_store=TranscriptStore(run_dir=run_dir, run_id=run_id),
        version=VersionContext(),
        state=RuntimeState(status="planner_eval"),
    )


def _action_for_case(case: PlannerEvalCase) -> ActionContract:
    return ActionContract(
        action_type="click",
        intent=f"Click {case.click}",
        target_hint=case.click or "",
        preferred_roles=["button", "link"],
        preconditions=["target_visible", "target_enabled"],
        expected_effect=_expected_effect(case.expect_text),
        risk_level="read_only",
    )


def _expected_effect(expect_text: str | None) -> ExpectedEffect:
    if expect_text:
        return ExpectedEffect(type="content_appears", value=expect_text)
    return ExpectedEffect(type="none")


def _as_url(value: str) -> str:
    if value.startswith(("http://", "https://", "file://")):
        return value
    return Path(value).resolve().as_uri()


def _error_type_from_exception(exc: RuntimeError) -> str:
    message = str(exc)
    if ":" in message:
        return message.split(":", 1)[0].strip()
    return "TOOL_CALL_PARSE_ERROR"


def _parsed_tool_ids_from_planner(planner: LLMTaskPlanner) -> list[str]:
    parse_result = (
        planner.repair_parse_results[-1]
        if planner.repair_parse_results
        else planner.last_parse_result
    )
    if parse_result is None:
        return []
    return [tool_call.tool_id for tool_call in parse_result.tool_calls]


def _case_passed(
    case: PlannerEvalCase,
    status: str,
    error_type: str | None,
    parsed_tool_ids: list[str],
) -> bool:
    if status != case.expected_status:
        return False
    if case.expected_error_type and error_type != case.expected_error_type:
        return False
    if case.expected_tool_ids and parsed_tool_ids != case.expected_tool_ids:
        return False
    return True


def _summarize(
    run_id: str,
    results: list[PlannerEvalCaseResult],
) -> PlannerEvalSummary:
    total_cases = len(results)
    passed_cases = sum(1 for result in results if result.passed)
    parse_success_cases = sum(1 for result in results if result.parsed_tool_ids)
    validation_success_cases = sum(
        1 for result in results if result.validation_status == "success"
    )
    repair_used_cases = sum(1 for result in results if result.repair_used)
    return PlannerEvalSummary(
        run_id=run_id,
        total_cases=total_cases,
        passed_cases=passed_cases,
        failed_cases=total_cases - passed_cases,
        success_rate=passed_cases / total_cases if total_cases else 0.0,
        parse_success_cases=parse_success_cases,
        validation_success_cases=validation_success_cases,
        repair_used_cases=repair_used_cases,
        results=results,
    )
