from __future__ import annotations

import json
import asyncio
from pathlib import Path
from time import perf_counter
from typing import Any

from webscoper.runtime.control import TaskControlStore
from webscoper.runtime.llm.client import (
    BaseLLMClient,
    FakeLLMClient,
    LLMProviderTimeoutError,
    OpenAICompatibleLLMClient,
)
from webscoper.runtime.llm.budget import (
    BudgetApprovalRequired,
    BudgetHardLimitExceeded,
    append_budget_decision,
    build_estimate,
    compact_llm_messages,
    decide_budget,
    emit_budget_checked,
    maybe_create_budget_approval,
)
from webscoper.runtime.llm.config import (
    load_llm_router_config,
    provider_config_to_client_config,
    resolve_llm_provider_config,
)
from webscoper.runtime.execution.events import TaskEventSink
from webscoper.runtime.safety.approvals import ApprovalStore
from webscoper.schemas.llm import LLMRequest, LLMResponse
from webscoper.schemas.runtime import BudgetContext


class LLMProviderRouter:
    def __init__(self, config_path: Path | None = None) -> None:
        self.config_path = config_path
        self.router_config = load_llm_router_config(config_path)

    def create_client(
        self,
        provider_id: str | None = None,
        model_override: str | None = None,
        *,
        run_dir: Path | None = None,
        task_id: str | None = None,
        purpose: str = "planner",
        budget: BudgetContext | None = None,
        event_sink: TaskEventSink | None = None,
        approval_store: ApprovalStore | None = None,
        control_store: TaskControlStore | None = None,
        user_goal: str | None = None,
    ) -> BaseLLMClient:
        provider = resolve_llm_provider_config(
            self.router_config,
            provider_id=provider_id,
            model_override=model_override,
        )
        if provider.provider_type in {"fake", "mock"}:
            client: BaseLLMClient = FakeLLMClient()
            return _wrap_for_audit(
                client,
                provider=provider.provider_id,
                model=provider.model,
                mode=provider.mode or self.router_config.mode,
                run_dir=run_dir,
                task_id=task_id,
                purpose=purpose,
                budget=_budget_from_config(self.router_config.budget, budget),
                event_sink=event_sink,
                approval_store=approval_store,
                control_store=control_store,
                user_goal=user_goal,
            )
        if provider.provider_type == "openai_compatible":
            client = OpenAICompatibleLLMClient(provider_config_to_client_config(provider))
            return _wrap_for_audit(
                client,
                provider=provider.provider_id,
                model=provider.model,
                fallback_model=provider.fallback_model,
                mode=provider.mode or self.router_config.mode,
                run_dir=run_dir,
                task_id=task_id,
                purpose=purpose,
                budget=_budget_from_config(self.router_config.budget, budget),
                event_sink=event_sink,
                approval_store=approval_store,
                control_store=control_store,
                user_goal=user_goal,
            )
        raise ValueError(
            f"Unsupported LLM provider_type for {provider.provider_id}: "
            f"{provider.provider_type}"
        )


class LLMTimeoutApprovalRequired(RuntimeError):
    def __init__(self, approval_id: str) -> None:
        super().__init__(f"LLM timeout approval required: {approval_id}")
        self.approval_id = approval_id


class AuditedBudgetedLLMClient(BaseLLMClient):
    def __init__(
        self,
        client: BaseLLMClient,
        *,
        provider: str,
        model: str,
        mode: str,
        audit_path: Path | None,
        task_id: str | None,
        purpose: str,
        budget: BudgetContext,
        event_sink: TaskEventSink | None = None,
        approval_store: ApprovalStore | None = None,
        control_store: TaskControlStore | None = None,
        user_goal: str | None = None,
        fallback_model: str | None = None,
    ) -> None:
        self.client = client
        self.provider = provider
        self.model = model
        self.fallback_model = fallback_model
        self.mode = mode
        self.audit_path = audit_path
        self.task_id = task_id or "unknown"
        self.purpose = purpose
        self.budget = budget
        self.calls_made = _existing_call_count(audit_path)
        prompt_total, completion_total = _existing_token_totals(audit_path)
        self.prompt_tokens_total = prompt_total
        self.completion_tokens_total = completion_total
        self.total_tokens = prompt_total + completion_total
        self.event_sink = event_sink
        self.approval_store = approval_store
        self.control_store = control_store
        self.user_goal = user_goal

    async def generate(self, request: LLMRequest) -> LLMResponse:
        if (
            self.approval_store is None
            and self.event_sink is None
            and self.control_store is None
            and _legacy_prompt_budget_exceeded(self.budget, request)
        ):
            prompt_tokens = _estimate_request_tokens(request)
            call_id = f"{self.purpose}_{self.calls_made + 1:04d}"
            self._write_audit(
                call_id=call_id,
                prompt_tokens=prompt_tokens,
                completion_tokens=0,
                duration_ms=0,
                status="skipped",
                error_type="LLM_BUDGET_EXCEEDED",
                budget_decision="max_prompt_tokens_exceeded",
                response_preview=None,
            )
            raise RuntimeError("LLM budget exceeded: max_prompt_tokens_exceeded")

        prompt_tokens = _estimate_request_tokens(request)
        request = request.model_copy(
            update={"max_tokens": min(request.max_tokens, self.budget.max_completion_tokens_per_call)}
        )
        estimate = self._estimate(prompt_tokens, request.max_tokens)
        control = self.control_store.get(self.task_id) if self.control_store else None
        budget_decision = decide_budget(
            self.budget,
            estimate,
            continue_for_task=bool(control and control.continue_for_task),
        )
        compaction_applied = False
        if control and control.aggressive_compaction_requested:
            self._emit(
                "budget_compaction_started",
                "Prompt compaction started",
                {"run_id": self.task_id, "purpose": self.purpose, "mode": "aggressive"},
            )
            request = request.model_copy(
                update={
                    "messages": compact_llm_messages(
                        request.messages,
                        max_prompt_tokens=max(1, self.budget.max_prompt_tokens_per_call // 2),
                    )
                }
            )
            prompt_tokens = _estimate_request_tokens(request)
            estimate = self._estimate(prompt_tokens, request.max_tokens)
            compaction_applied = True
            budget_decision = decide_budget(
                self.budget,
                estimate,
                continue_for_task=bool(control and control.continue_for_task),
                per_call_compacted=True,
            )
            self._emit(
                "budget_compaction_finished",
                "Prompt compaction finished",
                {
                    "run_id": self.task_id,
                    "purpose": self.purpose,
                    "estimated_prompt_tokens": prompt_tokens,
                    "decision": budget_decision,
                    "mode": "aggressive",
                },
            )
        elif budget_decision == "compaction_required":
            self._emit(
                "budget_compaction_started",
                "Prompt compaction started",
                {"run_id": self.task_id, "purpose": self.purpose},
            )
            request = request.model_copy(
                update={
                    "messages": compact_llm_messages(
                        request.messages,
                        max_prompt_tokens=max(1, self.budget.max_prompt_tokens_per_call - 256),
                    )
                }
            )
            prompt_tokens = _estimate_request_tokens(request)
            estimate = self._estimate(prompt_tokens, request.max_tokens)
            compaction_applied = True
            budget_decision = decide_budget(
                self.budget,
                estimate,
                continue_for_task=bool(control and control.continue_for_task),
                per_call_compacted=True,
            )
            self._emit(
                "budget_compaction_finished",
                "Prompt compaction finished",
                {
                    "run_id": self.task_id,
                    "purpose": self.purpose,
                    "estimated_prompt_tokens": prompt_tokens,
                    "decision": budget_decision,
                },
            )

        append_budget_decision(
            self.audit_path.parent if self.audit_path is not None else None,
            task_id=self.task_id,
            decision=budget_decision,
            provider=self.provider,
            model=self.model,
            purpose=self.purpose,
            budget=self.budget,
            estimate=estimate,
            compaction_applied=compaction_applied,
        )
        emit_budget_checked(
            self.event_sink,
            task_id=self.task_id,
            decision=budget_decision,
            provider=self.provider,
            model=self.model,
            budget=self.budget,
            estimate=estimate,
            compaction_applied=compaction_applied,
        )
        started = perf_counter()
        call_id = f"{self.purpose}_{self.calls_made + 1:04d}"
        if budget_decision == "warning":
            self._emit(
                "budget_warning",
                "LLM budget soft threshold exceeded",
                {
                    "run_id": self.task_id,
                    "purpose": self.purpose,
                    "prompt_tokens_so_far": estimate.prompt_tokens_so_far,
                    "estimated_prompt_tokens_next_call": estimate.prompt_tokens_next_call,
                },
            )
        elif budget_decision == "approval_required" and not (
            control and (control.budget_override or control.continue_for_task)
        ):
            approval_id = maybe_create_budget_approval(
                approval_store=self.approval_store,
                control_store=self.control_store,
                event_sink=self.event_sink,
                task_id=self.task_id,
                run_dir=self.audit_path.parent if self.audit_path is not None else None,
                provider=self.provider,
                model=self.model,
                purpose=self.purpose,
                user_goal=self.user_goal,
                budget=self.budget,
                estimate=estimate,
            )
            self._write_audit(
                call_id=call_id,
                prompt_tokens=prompt_tokens,
                completion_tokens=0,
                duration_ms=0,
                status="skipped",
                error_type="LLM_BUDGET_EXCEEDED",
                budget_decision=budget_decision,
                response_preview=None,
            )
            raise BudgetApprovalRequired(approval_id or "unknown")
        elif budget_decision in {"hard_limit_exceeded", "denied", "compaction_required"}:
            self._write_audit(
                call_id=call_id,
                prompt_tokens=prompt_tokens,
                completion_tokens=0,
                duration_ms=0,
                status="skipped",
                error_type="LLM_BUDGET_EXCEEDED",
                budget_decision=budget_decision,
                response_preview=None,
            )
            if budget_decision == "hard_limit_exceeded":
                self._emit(
                    "budget_hard_limit_exceeded",
                    "Hard LLM context limit exceeded",
                    {
                        "run_id": self.task_id,
                        "purpose": self.purpose,
                        "estimated_prompt_tokens": prompt_tokens,
                    },
                )
                raise BudgetHardLimitExceeded(
                    "Hard LLM context limit exceeded; task stopped after saving partial evidence."
                )
            raise RuntimeError(f"LLM budget exceeded: {budget_decision}")
        elif control and control.budget_override:
            self.control_store.clear_transient_flags(self.task_id)

        max_retries = (
            max(0, self.budget.max_llm_retries_per_call)
            if self.budget.retry_on_llm_timeout
            else 0
        )
        timeout_error: LLMProviderTimeoutError | None = None
        for attempt in range(max_retries + 1):
            attempt_call_id = call_id if attempt == 0 else f"{call_id}_retry_{attempt}"
            if attempt > 0:
                self._emit(
                    "llm_retry_started",
                    "LLM retry started",
                    self._llm_event_payload(
                        status="running",
                        duration_ms=0,
                        error_type=None,
                        error_message=None,
                        retryable=True,
                        attempt=attempt,
                        max_retries=max_retries,
                    ),
                )
            try:
                response = await self.client.generate(request)
                completion_tokens = _estimate_text_tokens(response.content)
                self.calls_made += 1
                self.prompt_tokens_total += prompt_tokens
                self.completion_tokens_total += completion_tokens
                self.total_tokens += prompt_tokens + completion_tokens
                duration_ms = int((perf_counter() - started) * 1000)
                self._write_audit(
                    call_id=attempt_call_id,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    duration_ms=duration_ms,
                    status="success",
                    error_type=None,
                    budget_decision=budget_decision,
                    response_preview=_preview_text(response.content),
                    retryable=False,
                )
                self._emit_llm_finished(
                    status="success",
                    duration_ms=duration_ms,
                    error_type=None,
                    error_message=None,
                    retryable=False,
                    attempt=attempt,
                    max_retries=max_retries,
                )
                if attempt > 0:
                    self._emit(
                        "llm_retry_finished",
                        "LLM retry finished",
                        self._llm_event_payload(
                            status="success",
                            duration_ms=duration_ms,
                            error_type=None,
                            error_message=None,
                            retryable=False,
                            attempt=attempt,
                            max_retries=max_retries,
                        ),
                    )
                return response
            except LLMProviderTimeoutError as exc:
                timeout_error = exc
                self.calls_made += 1
                duration_ms = int((perf_counter() - started) * 1000)
                self._write_audit(
                    call_id=attempt_call_id,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=0,
                    duration_ms=duration_ms,
                    status="failed",
                    error_type="LLM_PROVIDER_TIMEOUT",
                    budget_decision=budget_decision,
                    response_preview=None,
                    retryable=True,
                )
                self._emit_llm_finished(
                    status="failed",
                    duration_ms=duration_ms,
                    error_type="LLM_PROVIDER_TIMEOUT",
                    error_message=str(exc),
                    retryable=True,
                    attempt=attempt,
                    max_retries=max_retries,
                )
                if attempt > 0:
                    self._emit(
                        "llm_retry_finished",
                        "LLM retry finished",
                        self._llm_event_payload(
                            status="failed",
                            duration_ms=duration_ms,
                            error_type="LLM_PROVIDER_TIMEOUT",
                            error_message=str(exc),
                            retryable=True,
                            attempt=attempt,
                            max_retries=max_retries,
                        ),
                    )
                if attempt < max_retries:
                    self._emit(
                        "llm_retry_scheduled",
                        "LLM retry scheduled after provider timeout",
                        self._llm_event_payload(
                            status="scheduled",
                            duration_ms=duration_ms,
                            error_type="LLM_PROVIDER_TIMEOUT",
                            error_message=str(exc),
                            retryable=True,
                            attempt=attempt + 1,
                            max_retries=max_retries,
                        ),
                    )
                    await asyncio.sleep(1)
                    continue
                approval_id = self._create_timeout_approval(
                    error_message=str(exc),
                    timeout_ms=_client_timeout_ms(self.client),
                    prompt_tokens=prompt_tokens,
                )
                raise LLMTimeoutApprovalRequired(approval_id) from exc
            except Exception as exc:
                self.calls_made += 1
                duration_ms = int((perf_counter() - started) * 1000)
                self._write_audit(
                    call_id=attempt_call_id,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=0,
                    duration_ms=duration_ms,
                    status="failed",
                    error_type=type(exc).__name__,
                    budget_decision=budget_decision,
                    response_preview=None,
                    retryable=False,
                )
                self._emit_llm_finished(
                    status="failed",
                    duration_ms=duration_ms,
                    error_type=type(exc).__name__,
                    error_message=str(exc),
                    retryable=False,
                    attempt=attempt,
                    max_retries=max_retries,
                )
                raise
        if timeout_error is not None:
            raise timeout_error
        raise RuntimeError("LLM call failed without a provider response.")

    def _budget_decision(self, prompt_tokens: int) -> str:
        if self.calls_made >= self.budget.max_llm_calls_per_task:
            return "max_llm_calls_per_task_exceeded"
        if prompt_tokens > self.budget.max_prompt_tokens:
            return "max_prompt_tokens_exceeded"
        if self.total_tokens + prompt_tokens > self.budget.max_total_tokens_per_task:
            return "max_total_tokens_per_task_exceeded"
        return "allowed"

    def _estimate(self, prompt_tokens: int, max_completion_tokens: int):
        return build_estimate(
            prompt_tokens_next_call=prompt_tokens,
            max_completion_tokens_next_call=max_completion_tokens,
            prompt_tokens_so_far=self.prompt_tokens_total,
            completion_tokens_so_far=self.completion_tokens_total,
            llm_calls_so_far=self.calls_made,
        )

    def _emit(
        self,
        kind: str,
        message: str,
        payload: dict[str, Any],
    ) -> None:
        if self.event_sink is None:
            return
        try:
            self.event_sink(kind, message, payload)
        except Exception:
            return

    def _emit_llm_finished(
        self,
        *,
        status: str,
        duration_ms: int,
        error_type: str | None,
        error_message: str | None,
        retryable: bool,
        attempt: int,
        max_retries: int,
    ) -> None:
        self._emit(
            "llm_call_finished",
            "LLM call finished",
            self._llm_event_payload(
                status=status,
                duration_ms=duration_ms,
                error_type=error_type,
                error_message=error_message,
                retryable=retryable,
                attempt=attempt,
                max_retries=max_retries,
            ),
        )

    def _llm_event_payload(
        self,
        *,
        status: str,
        duration_ms: int,
        error_type: str | None,
        error_message: str | None,
        retryable: bool,
        attempt: int,
        max_retries: int,
    ) -> dict[str, Any]:
        return {
            "run_id": self.task_id,
            "status": status,
            "provider": self.provider,
            "model": self.model,
            "purpose": self.purpose,
            "duration_ms": duration_ms,
            "error_type": error_type,
            "error_message": error_message,
            "timeout_ms": _client_timeout_ms(self.client),
            "retryable": retryable,
            "attempt": attempt,
            "max_retries": max_retries,
        }

    def _create_timeout_approval(
        self,
        *,
        error_message: str,
        timeout_ms: int | None,
        prompt_tokens: int,
    ) -> str:
        if self.approval_store is None:
            raise LLMProviderTimeoutError(error_message)
        existing = [
            approval
            for approval in self.approval_store.list_for_task(self.task_id)
            if approval.status == "pending"
            and approval.metadata.get("approval_type") == "llm_timeout"
        ]
        if existing:
            return existing[-1].approval_id
        metadata = {
            "approval_type": "llm_timeout",
            "provider": self.provider,
            "model": self.model,
            "fallback_model": self.fallback_model,
            "purpose": self.purpose,
            "timeout_ms": timeout_ms,
            "estimated_prompt_tokens_next_call": prompt_tokens,
            "user_goal": self.user_goal,
            "suggested_options": [
                "retry_same_model",
                "retry_with_faster_model",
                "stop_and_summarize",
                "cancel_task",
            ],
        }
        approval = self.approval_store.create_request(
            task_id=self.task_id,
            reason="The LLM provider did not respond before the timeout.",
            risk_level="low",
            tool_name="llm_timeout",
            action_type="timeout_approval",
            target_hint=self.purpose,
            metadata=metadata,
        )
        run_dir = self.audit_path.parent if self.audit_path is not None else None
        if run_dir is not None:
            self.approval_store.write_jsonl_for_task(self.task_id, run_dir / "approvals.jsonl")
        self._emit(
            "approval_required",
            "Approval required after LLM provider timeout",
            {
                "run_id": self.task_id,
                "approval_request": approval.model_dump(mode="json"),
                "error_type": "LLM_PROVIDER_TIMEOUT",
                "error_message": error_message,
            },
        )
        return approval.approval_id

    def _write_audit(
        self,
        *,
        call_id: str,
        prompt_tokens: int,
        completion_tokens: int,
        duration_ms: int,
        status: str,
        error_type: str | None,
        budget_decision: str,
        response_preview: str | None,
        retryable: bool | None = None,
    ) -> None:
        if self.audit_path is None:
            return
        self.audit_path.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "timestamp": _utc_now(),
            "task_id": self.task_id,
            "call_id": call_id,
            "provider": self.provider,
            "model": self.model,
            "mode": self.mode,
            "purpose": self.purpose,
            "prompt_tokens_estimated": prompt_tokens,
            "completion_tokens_estimated": completion_tokens,
            "duration_ms": duration_ms,
            "status": status,
            "error_type": error_type,
            "retryable": retryable,
            "timeout_ms": _client_timeout_ms(self.client),
            "budget_decision": budget_decision,
            "response_preview": response_preview,
            "response_redacted": response_preview is not None,
        }
        with self.audit_path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(record, ensure_ascii=False) + "\n")


def _wrap_for_audit(
    client: BaseLLMClient,
    *,
    provider: str,
    model: str,
    fallback_model: str | None = None,
    mode: str,
    run_dir: Path | None,
    task_id: str | None,
    purpose: str,
    budget: BudgetContext,
    event_sink: TaskEventSink | None = None,
    approval_store: ApprovalStore | None = None,
    control_store: TaskControlStore | None = None,
    user_goal: str | None = None,
) -> BaseLLMClient:
    audit_path = run_dir / "llm_calls.jsonl" if run_dir is not None else None
    return AuditedBudgetedLLMClient(
        client,
        provider=provider,
        model=model,
        mode=mode,
        audit_path=audit_path,
        task_id=task_id,
        purpose=purpose,
        budget=budget,
        event_sink=event_sink,
        approval_store=approval_store,
        control_store=control_store,
        user_goal=user_goal,
        fallback_model=fallback_model,
    )


def _budget_from_config(
    payload: dict[str, Any],
    fallback: BudgetContext | None,
) -> BudgetContext:
    base = fallback or BudgetContext()
    if not payload:
        return base
    return base.model_copy(
        update={
            key: value
            for key, value in payload.items()
            if key in BudgetContext.model_fields
        }
    )


def _estimate_request_tokens(request: LLMRequest) -> int:
    return sum(_estimate_text_tokens(message.content) for message in request.messages)


def _estimate_text_tokens(value: str) -> int:
    return max(1, (len(value) + 3) // 4) if value else 0


def _preview_text(value: str, limit: int = 2000) -> str:
    return value if len(value) <= limit else value[:limit] + "...[truncated]"


def _existing_call_count(path: Path | None) -> int:
    if path is None or not path.exists():
        return 0
    count = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if payload.get("status") != "skipped":
            count += 1
    return count


def _existing_token_total(path: Path | None) -> int:
    prompt, completion = _existing_token_totals(path)
    return prompt + completion


def _existing_token_totals(path: Path | None) -> tuple[int, int]:
    if path is None or not path.exists():
        return 0, 0
    prompt_total = 0
    completion_total = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if payload.get("status") == "skipped":
            continue
        prompt_total += int(payload.get("prompt_tokens_estimated") or 0)
        completion_total += int(payload.get("completion_tokens_estimated") or 0)
    return prompt_total, completion_total


def _legacy_prompt_budget_exceeded(budget: BudgetContext, request: LLMRequest) -> bool:
    fields_set = getattr(budget, "model_fields_set", set())
    if "max_prompt_tokens" not in fields_set or "max_prompt_tokens_per_call" in fields_set:
        return False
    return _estimate_request_tokens(request) > budget.max_prompt_tokens


def _client_timeout_ms(client: BaseLLMClient) -> int | None:
    config = getattr(client, "config", None)
    timeout_ms = getattr(config, "timeout_ms", None)
    if isinstance(timeout_ms, int):
        return timeout_ms
    return None


def _utc_now() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).isoformat()
