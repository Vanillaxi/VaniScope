from __future__ import annotations

import json
from pathlib import Path
from time import perf_counter
from typing import Any

from webscoper.runtime.llm.client import BaseLLMClient, FakeLLMClient, OpenAICompatibleLLMClient
from webscoper.runtime.llm.config import (
    load_llm_router_config,
    provider_config_to_client_config,
    resolve_llm_provider_config,
)
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
            )
        if provider.provider_type == "openai_compatible":
            client = OpenAICompatibleLLMClient(provider_config_to_client_config(provider))
            return _wrap_for_audit(
                client,
                provider=provider.provider_id,
                model=provider.model,
                mode=provider.mode or self.router_config.mode,
                run_dir=run_dir,
                task_id=task_id,
                purpose=purpose,
                budget=_budget_from_config(self.router_config.budget, budget),
            )
        raise ValueError(
            f"Unsupported LLM provider_type for {provider.provider_id}: "
            f"{provider.provider_type}"
        )


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
    ) -> None:
        self.client = client
        self.provider = provider
        self.model = model
        self.mode = mode
        self.audit_path = audit_path
        self.task_id = task_id or "unknown"
        self.purpose = purpose
        self.budget = budget
        self.calls_made = _existing_call_count(audit_path)
        self.total_tokens = _existing_token_total(audit_path)

    async def generate(self, request: LLMRequest) -> LLMResponse:
        prompt_tokens = _estimate_request_tokens(request)
        budget_decision = self._budget_decision(prompt_tokens)
        started = perf_counter()
        call_id = f"{self.purpose}_{self.calls_made + 1:04d}"
        if budget_decision != "allowed":
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
            raise RuntimeError(f"LLM budget exceeded: {budget_decision}")

        try:
            response = await self.client.generate(request)
            completion_tokens = _estimate_text_tokens(response.content)
            self.calls_made += 1
            self.total_tokens += prompt_tokens + completion_tokens
            self._write_audit(
                call_id=call_id,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                duration_ms=int((perf_counter() - started) * 1000),
                status="success",
                error_type=None,
                budget_decision=budget_decision,
                response_preview=_preview_text(response.content),
            )
            return response
        except Exception as exc:
            self.calls_made += 1
            self._write_audit(
                call_id=call_id,
                prompt_tokens=prompt_tokens,
                completion_tokens=0,
                duration_ms=int((perf_counter() - started) * 1000),
                status="failed",
                error_type=type(exc).__name__,
                budget_decision=budget_decision,
                response_preview=None,
            )
            raise

    def _budget_decision(self, prompt_tokens: int) -> str:
        if self.calls_made >= self.budget.max_llm_calls_per_task:
            return "max_llm_calls_per_task_exceeded"
        if prompt_tokens > self.budget.max_prompt_tokens:
            return "max_prompt_tokens_exceeded"
        if self.total_tokens + prompt_tokens > self.budget.max_total_tokens_per_task:
            return "max_total_tokens_per_task_exceeded"
        return "allowed"

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
    mode: str,
    run_dir: Path | None,
    task_id: str | None,
    purpose: str,
    budget: BudgetContext,
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
    return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())


def _existing_token_total(path: Path | None) -> int:
    if path is None or not path.exists():
        return 0
    total = 0
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        total += int(payload.get("prompt_tokens_estimated") or 0)
        total += int(payload.get("completion_tokens_estimated") or 0)
    return total


def _utc_now() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).isoformat()
