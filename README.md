# VaniScope

[中文说明](README_CN.md)

VaniScope / Web-Scoper is a LangGraph-based browser-agent runtime for local and fixture-based web task execution. It includes browser observation and click intent, deterministic and LLM-backed planning modes, evidence/report artifacts, reviewer and revise-loop support, FastAPI task APIs, risk-gated approval pause/resume, context compaction, a LangGraph workflow backend, regression evals for workflow behavior, and a Next.js 16 control console.

The runtime package is split by responsibility into `runtime/execution`, `runtime/artifacts`, `runtime/inspector`, `runtime/llm`, `runtime/prompt`, `runtime/review`, and `runtime/safety`. Runtime root-level compatibility re-exports have been removed; project code imports the concrete package paths directly.

`webscoper/workflows/langgraph_adapter.py` remains the public LangGraph workflow entry point. Its orchestration internals live under `webscoper/workflows/langgraph_backend/`. LangGraph is the only task orchestration layer.

`webscoper/tools/gateway/` contains the formal tool invocation entry point. LangGraph tool nodes call `ToolGateway.invoke()`, which applies policy, risk/approval decisions, provider dispatch, and `tool_audit.jsonl` audit records. Browser Runtime is exposed as a ToolGateway provider, and `FakeMCPToolProvider` gives deterministic local MCP-shaped tools for tests.

Browser recovery is split into `browser/recovery/classifier`, `planner`, `strategies`, `executor`, and `telemetry`, with `browser/recovery/manager.py` kept as the public facade.

`webscoper/skills/` contains the LangGraph skill layer. The default registry
currently ships `docs_research` and `github_issue_research`. Both read local
fixtures through the normal Browser Runtime and ToolGateway path, then produce
evidence-backed `final_report.md`, `review.json`, and `skill_result.json`
artifacts. The GitHub issue skill uses a mock issue fixture only and does not
access GitHub or the GitHub API.

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

Default pytest keeps workflow coverage to focused smoke cases. Run the explicit workflow eval command below when you want the full recovery/approval regression matrix.

## Control Console

The Next.js 16 control console lives in `apps/web` and talks only to the FastAPI Task API. It can create and complete local LangGraph browser tasks, stream task events over SSE, inspect artifacts, handle approvals, view evidence/review/report outputs, and show the local eval command helper.

The console is now organized as a ChatGPT-style task workspace: the sidebar has
`+ New Task`, skill shortcuts, API health, language switching, and a recent task
history stored in browser `localStorage`. Skill selection lives in the sidebar
and home-page skill cards instead of a large mixed form; `/tasks/new?skill=...`
renders fields specific to Browser Task, Docs Research, or GitHub Issue Research.
Task detail pages include a Runtime Inspector with Timeline, Artifacts,
Evidence, LLM / Prompt, Review, and Approval tabs. The inspector is backed by
`/tasks/{task_id}/timeline` and `/tasks/{task_id}/inspector`, which dynamically
aggregate run artifacts without a database.

Next.js 16 控制台位于 `apps/web`，只对接 FastAPI Task API。它支持完整跑通本地 LangGraph 浏览器任务，通过 SSE 查看实时事件，检查 artifacts，处理审批，查看 evidence / review / report 输出，并提供本地 eval 命令辅助页。

Start the API:

启动 API：

```bash
uv run python scripts/run_api.py
```

Configure and start the console:

配置并启动前端：

```bash
cd apps/web
pnpm install
pnpm dev
```

Open `http://localhost:3000`. The console reads:

访问 `http://localhost:3000`。控制台读取：

```bash
NEXT_PUBLIC_VANISCOPE_API_BASE_URL=http://localhost:8000
```

Copy `apps/web/.env.example` to a local `.env` if you need a different API base URL.

如果 API 地址不同，可以基于 `apps/web/.env.example` 创建本地 `.env`。

Full-stack demo / 完整链路 demo:

```text
docs/demo_next_console.md
```

## Project Layout

```text
webscoper/
  browser/       # Browser Runtime: Playwright session, observation, targeting, effects, recovery, risk signals
  runtime/       # Agent Runtime: execution, artifacts, inspector, LLM, prompt, review, safety
  skills/        # Skill definitions, registry, deterministic router, docs and GitHub issue skills
  api/           # FastAPI Task API, async tasks, approvals, SSE event stream, artifact access
  eval/          # Browser, planner, reviewer, and workflow regression eval harnesses
  workflows/     # LangGraph backend orchestration modules
  tools/         # Tool registry, browser tool definitions, and ToolGateway providers
  schemas/       # Shared Pydantic schemas

apps/
  web/           # Next.js 16 control console for the FastAPI Task API

scripts/
  run_task.py
  run_api.py
  run_browser_eval.py
  run_planner_eval.py
  run_reviewer_eval.py
  run_workflow_eval.py
  run_langgraph_eval.py
  smoke_open_page.py

configs/
  llm.example.toml
  llm.local.toml  # local only, ignored

docs/
  runtime_modules.md
  runtime_inspector.md
  skills.md

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

LLM integration is intentionally controlled. Default task paths use deterministic
or fake planning and pytest does not require real LLM calls. Real providers must
be enabled through `configs/llm.local.toml` with `router.mode = "real"` and a
configured OpenAI-compatible provider. LLM readiness details, budget controls,
`prompt_preview.md`, `prompt_context.json`, `llm_calls.jsonl`, and dry-run mode
are documented in `docs/llm_readiness.md`.

## Workflow Eval

LangGraph workflow eval runs local task cases without real network or real LLM calls. The main fixture covers:

- workflow cases for status, artifacts, review, evidence, and compaction
- recovery cases for lazy controls, modal overlays, no-effect retries, ambiguous targets, disabled controls, login/password blocking, and captcha blocking
- approval cases for RiskGate approval-required decisions, task pause, approved resume, rejected stop, blocked delete actions, and persisted audit artifacts

```bash
uv run python scripts/run_workflow_eval.py \
  --cases tests/fixtures/langgraph_main_eval_cases.json \
  --output-dir eval_results/langgraph_eval_local
```

The runner writes `score.json` and `report.md` under the selected output directory. `score.json` includes total/pass/fail counts, recovery and approval pass counts, and LangGraph expectation failures.

Tool Gateway eval is LangGraph-first and verifies browser, local deterministic MCP-shaped tools, approval, blocking, and audit behavior:

```bash
uv run python scripts/run_workflow_eval.py \
  --cases tests/fixtures/tool_gateway_eval_cases.json \
  --output-dir eval_results/tool_gateway_eval_local
```

Skill eval verifies `docs_research` and `github_issue_research` with local
fixtures only:

```bash
uv run python scripts/run_langgraph_eval.py \
  --cases tests/fixtures/langgraph_skill_eval_cases.json \
  --output-dir eval_results/langgraph_skill_eval_local
```
