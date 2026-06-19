# LLM Readiness

VaniScope keeps real LLM access behind an explicit router because the core value
is the observable LangGraph Browser Agent Runtime: prompt context, budget,
trace, evidence, review, approval, and reproducible evals must work before a
real provider is allowed into the main path.

## Modes

- `deterministic`: no LLM call; deterministic planner/reviewer logic.
- `fake` / `mock`: local deterministic LLM-shaped behavior, still routed through
  budget and audit when used as a planner client.
- `real`: OpenAI-compatible provider, enabled only by an explicit TOML config
  with `router.mode = "real"` and a configured API key.

If no router config path is supplied, `LLMProviderRouter()` returns the built-in
fake provider. It does not silently read environment variables or local config.

## Config

Use `configs/llm.example.toml` as the committed template. For real local testing,
copy it to `configs/llm.local.toml`, set:

```toml
[router]
default_provider = "openai"
mode = "real"
```

Then fill the selected `[providers.<id>]` section. `configs/llm.local.toml`,
`configs/*.local.toml`, and `configs/llm.toml` are ignored by git.

## Budget

`BudgetContext` includes LLM limits:

- `max_llm_calls_per_task`
- `max_total_tokens_per_task`
- `max_prompt_tokens`
- `max_completion_tokens`
- `llm_timeout_seconds`

The audited client estimates tokens before calling the provider. If the call
would exceed budget, it writes a skipped audit record and raises before the
underlying fake/mock/real client is called.

## Audit

LLM calls append `llm_calls.jsonl` under the run directory. Each row records:

- timestamp
- task_id
- provider, model, mode
- purpose
- estimated prompt/completion tokens
- duration_ms
- status
- error_type
- budget_decision

API keys are never written to this artifact.

## Prompt Preview

Every normal or dry-run task writes:

- `prompt_preview.md`
- `prompt_context.json`

These contain the task, routed skill context, tool summary, safety/budget
context, runtime reminders, compact context hooks, and output schema before LLM
planning happens.

## Dry Run

`dry_run = true` builds context, routes the skill, writes prompt artifacts, writes
`dry_run_result.json`, and stops before LLM planning and browser execution. This
is intentionally minimal readiness support for reviewing prompt construction
without touching a real provider or browser action.

## Tests

Pytest defaults do not call real LLM providers. The LLM readiness tests cover
fake fallback, example config parsing, explicit real-mode errors, audit writing,
budget blocking, and dry-run prompt artifacts.
