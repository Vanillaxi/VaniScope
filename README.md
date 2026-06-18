# VaniScope

[中文说明](README_CN.md)

VaniScope / Web-Scoper is a Python browser-agent runtime for local and fixture-based web task execution. It includes browser observation and click intent, deterministic and LLM-backed planning modes, evidence/report artifacts, reviewer and revise-loop support, FastAPI task APIs, risk-gated approval pause/resume, context compaction, and native/LangGraph workflow backends.

The runtime package is split by responsibility into `runtime/execution`, `runtime/artifacts`, `runtime/llm`, `runtime/prompt`, `runtime/review`, and `runtime/safety`. Old flat runtime import paths are temporarily kept as a compatibility layer.

`webscoper/workflows/langgraph_adapter.py` remains the public LangGraph workflow entry point. Its orchestration internals live under `webscoper/workflows/langgraph_backend/`.

Browser recovery is split into `browser/recovery/classifier`, `planner`, `strategies`, `executor`, and `telemetry`, with `browser/recovery/manager.py` kept as the public facade.

## Scope

VaniScope does not bypass login, CAPTCHA, or paywalls. It does not enter real accounts, passwords, payment details, or identity documents. Risky actions are blocked or require local approval before execution.

## Smoke Test

```bash
uv run python scripts/smoke_open_page.py https://example.com
uv run python scripts/smoke_open_page.py https://example.com --headed
```

Each run creates `traces/<run_id>/trace.jsonl` and `traces/<run_id>/step_001.png`.

The terminal prints the run ID, final URL, page title, screenshot path, interactive element count, risk signal count, and trace path.

## Tests

```bash
uv run pytest
```

## Project Layout

```text
webscoper/
  browser/       # Browser Runtime: Playwright session, observation, targeting, effects, recovery, risk signals
  runtime/       # Agent Runtime: execution, artifacts, LLM, prompt, review, safety compatibility layer
  api/           # FastAPI Task API, async tasks, approvals, SSE event stream, artifact access
  eval/          # Browser, planner, and reviewer eval harnesses
  workflows/     # Native workflows and LangGraph backend orchestration modules
  tools/         # Tool registry and browser tool definitions
  schemas/       # Shared Pydantic schemas

scripts/
  run_task.py
  run_api.py
  run_browser_eval.py
  run_planner_eval.py
  run_reviewer_eval.py
  smoke_open_page.py

configs/
  llm.example.toml
  llm.local.toml  # local only, ignored

docs/
  compatibility_imports.md
  runtime_modules.md

runs/
  .gitkeep

traces/
  .gitkeep

eval_results/
  .gitkeep

tests/
  api/
  browser/
  eval/
  llm/
  runtime/
  workflows/
  fixtures/
```

## Configuration

Use `configs/llm.example.toml` as the committed template. Put local provider settings in `configs/llm.local.toml`; local config files and generated run/eval artifacts are ignored by git.
