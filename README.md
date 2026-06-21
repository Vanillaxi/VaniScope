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
* Public web access is disabled by default. Local fixtures, `file://`, localhost, and `127.0.0.1` remain the default operating surface.
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
mode: auto_explore
url: tests/fixtures/mock_site/basic.html
goal: Summarize the visible page information and collect evidence.
planner: fake_llm
workspace: tests/fixtures/workspace
```

Guided browser debug task:

```text
mode: guided
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

## Conversation Persistence and Auto Explore

VaniScope stores local conversation and task metadata in SQLite. The default path is `data/vaniscope.db`, configurable with `[persistence].sqlite_path` in `configs/runtime.local.toml` or `VANISCOPE_DB_PATH`. SQLite stores conversations, messages, task metadata, artifact paths/sizes, and approval metadata. Large artifacts such as traces, screenshots, prompts, and reports stay under `runs/task_xxx/`.

FastAPI includes:

```text
POST /conversations
GET /conversations
GET /conversations/{conversation_id}
GET /conversations/{conversation_id}/messages
POST /tasks
```

Browser tasks now support URL + natural-language goal through `mode: auto_explore`. Guided mode is still available for deterministic demos and debugging with explicit `click` / `expect` fields. Skill mode remains available for registered skills such as `docs_research` and `github_issue_research`.

The auto-explore loop lets an LLM choose structured action intents only:

```text
observe
click_intent
extract
ask_human
finish
```

The LLM never chooses CSS selectors, XPath, JavaScript, or DOM handles. It may provide a `target_hint`; Browser Runtime still resolves the target, and ToolGateway, PublicWebPolicy, RiskGate, Approval, PageReadinessDetector, TargetResolver, EffectVerifier, RecoveryManager, EvidenceStore, and task budgets continue to govern execution.

Webpage content is untrusted evidence, not instructions. Prompt-injection text on a page, such as instructions to ignore previous rules or click a destructive control, must still satisfy the user goal and safety policy before any action is attempted.

Fake/deterministic planning remains the test and CI default path. Real LLM execution is opt-in through local configuration such as `configs/llm.local.toml`; do not commit real keys. Pytest and workflow eval do not depend on real public web access or real LLM providers.

## Web Runtime Modes

VaniScope is local-first by default, but real public web access is a formal local runtime mode. It is never enabled by pytest, workflow eval, CI, or the default checked-in config.

Copy and edit the example config:

```bash
cp configs/runtime.example.toml configs/runtime.local.toml
```

Do not commit `configs/runtime.local.toml` or any `configs/*.local.toml`.

Modes:

* `local`: default. Allows local fixtures, `file://`, localhost, `127.0.0.1`, and `::1`; blocks public URLs.
* `public_safe`: allows public HTTP/HTTPS only when the domain matches `allowed_domains`.
* `public_open`: allows any public HTTP/HTTPS domain, usually with `allowed_domains = ["*"]`, for local manual exploration only.

`public_safe` example:

```toml
[web]
mode = "public_safe"
public_network_enabled = true
allowed_domains = ["github.com", "playwright.dev", "docs.python.org", "arxiv.org"]
max_pages_per_task = 3
request_delay_ms = 250
navigation_timeout_ms = 12000
```

The public URL policy classifies each `browser_open_observe` URL before navigation:

* local fixture / `file://`: allowed by default
* localhost / `127.0.0.1` / `::1`: allowed by default
* public `http` / `https`: blocked in `local`, allow-listed in `public_safe`, open in `public_open`
* private/internal network addresses and hostnames: blocked
* unsupported schemes such as `javascript:` or `data:`: blocked

Safety gates still apply in every mode: VaniScope does not bypass login, CAPTCHA, paywalls, access control, password fields, payment fields, PII fields, or destructive submit/publish/delete/payment actions.

## Public Web Smoke

Public web smoke is manual, non-deterministic, and not a benchmark.

Manual smoke cases live in:

```text
tests/fixtures/public_web_smoke_cases.example.json
```

Run them manually:

```bash
uv run python scripts/run_public_web_smoke.py \
  --config configs/runtime.local.toml \
  --cases tests/fixtures/public_web_smoke_cases.example.json
```

The runner writes `summary.json` plus task artifacts under `runs/`. It uses soft checks only: page opens, title exists, visible text is non-empty, and expected artifacts exist when a task succeeds. Public smoke is non-deterministic and is not a benchmark.

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
default_provider = "openai_compatible"

[providers.openai_compatible]
type = "openai_compatible"
base_url = "https://api.openai.com/v1"
api_key = "YOUR_API_KEY_HERE"
model = "gpt-4.1-mini"
timeout_seconds = 30
```

Public web mode and real LLM mode are independent switches: enabling one does not enable the other. Real public exploration needs both `configs/runtime.local.toml` public web access and `configs/llm.local.toml` with `router.mode = "real"`.

LLM calls go through budget control and are written to `llm_calls.jsonl`. API keys are never written into artifacts, diagnostics, or smoke summaries. Action validation failures are written to `action_validation.json`.

Manual real LLM smoke is opt-in and not part of pytest or CI:

```bash
uv run python scripts/run_real_llm_smoke.py \
  --cases tests/fixtures/real_llm_smoke_cases.example.json \
  --output-dir eval_results/real_llm_smoke_local
```

The smoke runner uses soft assertions and reports task status, final URL/title, action count, LLM call count, artifact presence, failure reason, and run directory.

Dry-run tasks generate `prompt_preview.md`, `prompt_context.json`, and `dry_run_result.json`, then stop before browser or LLM execution.

## Interview Demo Path

Use this path when showing VaniScope as a real Web Agent runtime, not just a log viewer.

Example task:

```text
URL: https://github.com/Vanillaxi
Goal: Summarize this user's open-source experience, main repositories, technical direction, and activity.
```

Demo flow:

1. Start the API and Console, then create a new task with `public_safe` web access, `auto_explore`, and `real_llm`.
2. Open `Timeline` first. Point out `planner_started`, `llm_call_finished`, `llm_action_proposed`, `tool_call_started`, browser open/navigation, readiness wait, extract/click, evidence, and report events.
3. Open `Graph`. Show the chain as `Task -> LLM -> ToolGateway -> Browser -> Readiness -> Evidence -> Report`.
4. Click the `browser_open` / `browser_open_observe` node. Show before/after URL, duration, screenshot evidence, readiness confidence, and signals such as DOM complete, skeleton/spinner/overlay absent, layout stability, and soft network quiet.
5. Click the LLM node. Show provider/model, proposed action, validation result, and whether repair was attempted. Confirm that API keys are not present in the payload.
6. Click `Evidence`. Show page screenshot evidence, text evidence, source URL, page title, and evidence ids used by the report.
7. Open `Report`. Explain that the final answer is built from `evidence.jsonl`, not from a hidden browser state.
8. If the task fails, switch back to `Graph` or `Timeline` and inspect recovery, failure screenshot, error node, and related trace payload.

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
* `graph.json`: execution graph for offline replay.
* `tool_audit.jsonl`: ToolGateway audit.
* `recovery.jsonl`: recovery strategy records.
* `approvals.jsonl` / `pending.jsonl` / `risk_report.json`: approval-related artifacts.
* `workflow_state.json`: LangGraph workflow state snapshot.
