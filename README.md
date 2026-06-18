# VaniScope

[中文说明](README_CN.md)

VaniScope / Web-Scoper is a LangGraph-based browser-agent runtime for local and fixture-based web task execution. It includes browser observation and click intent, deterministic and LLM-backed planning modes, evidence/report artifacts, reviewer and revise-loop support, FastAPI task APIs, risk-gated approval pause/resume, context compaction, a LangGraph workflow backend, and regression evals for workflow behavior.

The runtime package is split by responsibility into `runtime/execution`, `runtime/artifacts`, `runtime/llm`, `runtime/prompt`, `runtime/review`, and `runtime/safety`. Old flat runtime import paths are temporarily kept as a compatibility layer.

`webscoper/workflows/langgraph_adapter.py` remains the public LangGraph workflow entry point. Its orchestration internals live under `webscoper/workflows/langgraph_backend/`. LangGraph is the formal workflow orchestration layer; the native runner is retained only for direct execution, smoke tests, and compatibility imports.

`webscoper/tools/gateway/` contains the formal tool invocation entry point. LangGraph tool nodes call `ToolGateway.invoke()`, which applies policy, risk/approval decisions, provider dispatch, and `tool_audit.jsonl` audit records. Browser Runtime is exposed as a ToolGateway provider, and `FakeMCPToolProvider` gives deterministic local MCP-shaped tools for tests. Future real MCP servers and a Go control plane can attach behind this gateway abstraction.

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

Default pytest keeps workflow coverage to focused smoke cases and pure comparison tests. Run the explicit workflow eval command below when you want the full recovery/approval regression matrix.

## Project Layout

```text
webscoper/
  browser/       # Browser Runtime: Playwright session, observation, targeting, effects, recovery, risk signals
  runtime/       # Agent Runtime: execution, artifacts, LLM, prompt, review, safety compatibility layer
  api/           # FastAPI Task API, async tasks, approvals, SSE event stream, artifact access
  eval/          # Browser, planner, reviewer, and workflow regression eval harnesses
  workflows/     # LangGraph backend orchestration modules plus native compatibility path
  tools/         # Tool registry, browser tool definitions, and ToolGateway providers
  schemas/       # Shared Pydantic schemas

scripts/
  run_task.py
  run_api.py
  run_browser_eval.py
  run_planner_eval.py
  run_reviewer_eval.py
  run_workflow_eval.py
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

## Workflow Eval

Workflow regression eval compares native and LangGraph workflow backends across the same local task cases without real network or real LLM calls. The combined fixture covers:

- workflow cases for status, artifacts, review, evidence, and compaction
- recovery cases for lazy controls, modal overlays, no-effect retries, ambiguous targets, disabled controls, login/password blocking, and captcha blocking
- approval cases for RiskGate approval-required decisions, task pause, approved resume, rejected stop, blocked delete actions, and persisted audit artifacts

```bash
uv run python scripts/run_workflow_eval.py \
  --cases tests/fixtures/workflow_eval_cases.json \
  --output-dir eval_results/workflow_eval_local
```

The runner writes `score.json` and `report.md` under the selected output directory. `score.json` includes total/pass/fail counts, recovery and approval pass counts, native/LangGraph expectation failures, and comparison failures.

Tool Gateway eval is LangGraph-first and verifies browser, local deterministic MCP-shaped tools, approval, blocking, and audit behavior:

```bash
uv run python scripts/run_workflow_eval.py \
  --cases tests/fixtures/tool_gateway_eval_cases.json \
  --output-dir eval_results/tool_gateway_eval_local
```
