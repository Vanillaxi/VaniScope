# VaniScope

[中文](README_CN.md)

VaniScope / Web-Scoper is a local-first, replayable Browser Agent Runtime built with Python, FastAPI, LangGraph, Playwright, ToolGateway, evidence-based reporting, approval workflows, runtime artifact replay, regression evals, and a Next.js console.

It is a runtime for executing, auditing, and inspecting browser-agent workflows.

## Boundaries

* LangGraph is the workflow orchestration layer.
* The Browser Runtime uses Playwright and is primarily designed for local fixtures and controlled pages by default.
* ToolGateway is the governance boundary for tool invocation. It handles policy, risk, approval, provider dispatch, and `tool_audit.jsonl`.
* FastAPI provides task APIs, event streaming, artifact reads, approval decisions, resume, and diagnostics.
* Next.js is a local console, not a production SaaS frontend.
* Real LLM providers must be explicitly enabled through local configuration. Tests and demos do not depend on real LLMs by default.
* VaniScope does not bypass login, CAPTCHA, paywalls, or access controls. It also does not enter real sensitive information.

## Directory Boundaries

```text
webscoper/
  api/           FastAPI Task API, approvals, artifacts, diagnostics, resume
  browser/       Playwright runtime, observation, target resolution, effect verification, readiness, recovery
  eval/          LangGraph workflow eval runner
  runtime/       execution loop, artifacts, prompt, LLM, review, safety, inspector
  schemas/       Pydantic data contracts
  skills/        docs_research and github_issue_research
  tools/         tool registry and ToolGateway
  workflows/     LangGraph adapter, approval bridge, backend nodes

apps/web/        Next.js local console
scripts/         API, task, workflow eval, browser smoke entrypoints
tests/           focused regression tests and local fixtures
```

## Core Modules

`webscoper/browser` handles browser execution: `StatefulBrowserToolRuntime`, page observation, target resolution, effect verification, readiness, risk signals, and recovery.

`webscoper/runtime` handles the task lifecycle under LangGraph: prompt building, tool-call planning and validation, artifact writing, LLM routing, review, approval safety, and Runtime Inspector aggregation.

`webscoper.workflows.LangGraphWorkflowAdapter` is the public workflow entrypoint. The implementation lives under `webscoper/workflows/langgraph_backend/`.

`webscoper/tools/gateway` is the official tool invocation boundary. LangGraph nodes call `ToolGateway.invoke()`, and the gateway decides whether a tool call is allowed, blocked, waiting for approval, or dispatched to a provider.

`webscoper/skills` contains task-level capabilities. The default registry only includes `docs_research` and `github_issue_research`. Both use local fixtures and do not access real GitHub, external websites, or real MCP services.

## Local Run

Start the API:

```bash
uv run python scripts/run_api.py
```

Start the console:

```bash
cd apps/web
pnpm install
pnpm dev
```

Open:

```text
http://localhost:3000
```

Default API:

```text
http://localhost:8000
```

Health and diagnostics:

```text
GET /health
GET /diagnostics
```

If the API base URL is different, set it in `apps/web/.env`:

```bash
NEXT_PUBLIC_VANISCOPE_API_BASE_URL=http://localhost:8000
```

## Demo Inputs

Browser task:

```text
url: tests/fixtures/mock_site/basic.html
click: Quickstart
expect: pip install playwright
planner: deterministic
workspace: tests/fixtures/workspace
```

Docs Research:

```text
url: tests/fixtures/mock_site/docs_research.html
task_type: docs_research
skill_id: docs_research
query: How do I install and run VaniScope?
language: en
```

GitHub Issue Research:

```text
url: tests/fixtures/mock_site/github_issue_research.html
task_type: github_issue_research
skill_id: github_issue_research
query: Analyze whether this issue is worth doing and summarize difficulty, affected modules, and risks.
language: en
```

Approval demo:

```text
url: tests/fixtures/mock_site/risk_actions.html
click: Submit
expect: Submitted successfully
planner: deterministic
workspace: tests/fixtures/workspace
```

Recovery demo:

```text
url: tests/fixtures/mock_site/early_button_hydration.html
click: Quickstart
expect: pip install playwright
planner: deterministic
workspace: tests/fixtures/workspace
```

## Browser Reliability

VaniScope does not treat `domcontentloaded` or `networkidle` as the only completion signal. Real pages may involve hydration, skeleton screens, spinners, overlays, delayed SPA routing, or long polling.

`PageReadinessDetector` samples lightweight signals:

* document ready state
* URL/title/text stability
* interactive element count stability
* spinner/skeleton/overlay disappearance
* target visibility, enabled state, stability, and occlusion status
* soft network quiet

Readiness states include `ready`, `loading`, `degraded_ready`, and `timeout`.

`degraded_ready` only means the page is usable enough for safe observation or read-only extraction. It never bypasses login, CAPTCHA, payment, security, or PII boundaries.

The shared mock site only keeps reusable pages: basic, hydration recovery, risk actions, docs research, and GitHub issue research. Spinner, skeleton, overlay, SPA route delay, disabled target, and long-poll-like scenarios are tested through temporary pytest HTML pages.

## Runtime Inspector

Runtime Inspector reads existing artifacts from the run directory. It does not re-run tasks, access the network, or call real LLMs.

It aggregates:

* `events.jsonl`
* `trace.jsonl`
* `tool_audit.jsonl`
* `llm_calls.jsonl`
* `recovery.jsonl`
* `approvals.jsonl`
* `evidence.jsonl`
* `review.json`
* `prompt_preview.md`
* `prompt_context.json`
* `final_report.md`

FastAPI exposes:

```text
GET /tasks/{task_id}/timeline
GET /tasks/{task_id}/inspector
```

The console uses these APIs to display Timeline, Artifacts, Evidence, LLM / Prompt, Review, and Approval views.

## LLM Configuration

The default path is deterministic or fake LLM execution. Real providers are only enabled through local configuration:

```text
configs/llm.example.toml
configs/llm.local.toml
```

A real provider must explicitly set:

```toml
[router]
mode = "real"
```

LLM calls go through budget control and are written to `llm_calls.jsonl`. API keys are never written into artifacts.

Dry-run tasks generate `prompt_preview.md`, `prompt_context.json`, and `dry_run_result.json`, then stop before browser or LLM execution.

## Tests and Eval

Run pytest:

```bash
uv run pytest -q
```

Run workflow eval:

```bash
uv run python scripts/run_workflow_eval.py \
  --cases tests/fixtures/langgraph_main_eval_cases.json \
  --output-dir eval_results/langgraph_eval_local
```

Run ToolGateway eval:

```bash
uv run python scripts/run_workflow_eval.py \
  --cases tests/fixtures/tool_gateway_eval_cases.json \
  --output-dir eval_results/tool_gateway_eval_local
```

Run skill eval:

```bash
uv run python scripts/run_workflow_eval.py \
  --cases tests/fixtures/langgraph_skill_eval_cases.json \
  --output-dir eval_results/langgraph_skill_eval_local
```

## Common Artifacts

* `final_report.md`: final report.
* `evidence.jsonl`: evidence entries.
* `review.json` / `review_summary.md`: report review result.
* `trace.jsonl`: browser/runtime trace.
* `transcript.jsonl`: runtime transcript.
* `events.jsonl`: task events.
* `tool_audit.jsonl`: ToolGateway audit.
* `recovery.jsonl`: recovery strategy records.
* `approvals.jsonl` / `pending.jsonl` / `risk_report.json`: approval-related artifacts.
* `workflow_state.json`: LangGraph workflow state snapshot.
