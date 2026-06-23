# VaniScope

[中文](README_CN.md)

VaniScope is a local-first Browser Agent Runtime for executing, auditing, and replaying browser-agent workflows. The product line is now intentionally narrow:

```text
Next.js Console
-> FastAPI
-> LangGraph Workflow
-> Auto Explore Planner
-> ToolGateway
-> Browser Tool Contract v2
-> Browser Runtime / Playwright
-> Evidence / Report / Review
-> Inspector / Graph / Timeline
-> SQLite metadata persistence
```

The default path is deterministic or fake LLM execution against local fixtures. Real LLM providers and public web access are both opt-in local settings.

## Architecture

```text
webscoper/
  api/        FastAPI task, artifact, approval, resume, diagnostics APIs
  browser/    Playwright sessions, v2 browser actions, observation, readiness, recovery
  eval/       Workflow eval runner
  runtime/    execution, prompt, LLM, safety, artifacts, review, inspector, persistence
  schemas/    Domain contracts
  skills/     docs_research and github_issue_research
  tools/      Tool registry and ToolGateway
  workflows/  LangGraph adapter and backend

apps/web/     Next.js local console
scripts/      Current run/eval/smoke entrypoints
tests/        Focused high-value regression tests
```

`ToolGateway` is the official tool invocation boundary. LangGraph nodes call the gateway, which applies policy, risk checks, approval handling, provider dispatch, and `tool_audit.jsonl` logging.

`webscoper/browser` owns browser capabilities only: opening pages, observing, clicking, typing/selecting safe fixture inputs, scrolling, waiting, extracting, screenshots, readiness, and recovery. It does not own workflow planning, prompt logic, or report generation.

## Browser Tools

Browser Tool Contract v2 is the only first-class tool layer:

```text
browser_open
browser_observe
browser_click
browser_type
browser_select
browser_scroll
browser_wait
browser_extract
browser_screenshot
ask_human
finish_task
```

LLMs choose structured actions and natural-language `target_hint` values. They do not output selectors, XPath, Playwright code, JavaScript, or raw DOM handles. RiskGate, PublicWebPolicy, Approval, Evidence, Trace, Timeline, and Graph remain on the execution path.

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

Open `http://localhost:3000`. The default API base is `http://localhost:8000`; override it with `NEXT_PUBLIC_VANISCOPE_API_BASE_URL` in `apps/web/.env`.

## Configuration

Runtime config:

```bash
cp configs/runtime.example.toml configs/runtime.local.toml
```

LLM config:

```bash
cp configs/llm.example.toml configs/llm.local.toml
```

Do not commit local configs, databases, runs, traces, downloads, browser state, `.env`, `.next`, `node_modules`, caches, or eval output.

Public web modes:

```text
local        default; local fixtures, file://, localhost only
public_safe  allow-listed public domains only
public_open  unrestricted public HTTP/HTTPS for manual local exploration
```

Real LLM mode is independent from public web mode. Enabling one does not enable the other.

## Demo Inputs

Auto explore:

```text
mode: auto_explore
url: tests/fixtures/mock_site/basic.html
goal: Summarize the visible page information and collect evidence.
planner: fake_llm
workspace: tests/fixtures/workspace
```

Guided deterministic click:

```text
mode: guided
url: tests/fixtures/mock_site/basic.html
click: Quickstart
expect: pip install playwright
planner: deterministic
workspace: tests/fixtures/workspace
```

Docs research:

```text
url: tests/fixtures/mock_site/docs_research.html
task_type: docs_research
skill_id: docs_research
query: How do I install and run VaniScope?
language: en
```

GitHub issue research:

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

## Current Scripts

```bash
uv run python scripts/run_api.py
uv run python scripts/run_task.py --url tests/fixtures/mock_site/basic.html --planner deterministic
uv run python scripts/run_workflow_eval.py --cases tests/fixtures/langgraph_main_eval_cases.json --output-dir eval_results/langgraph_eval_local
uv run python scripts/run_public_web_smoke.py --config configs/runtime.local.toml --cases tests/fixtures/public_web_smoke_cases.example.json
uv run python scripts/run_real_llm_smoke.py --cases tests/fixtures/real_llm_smoke_cases.example.json --output-dir eval_results/real_llm_smoke_local
```

## Tests And Eval

```bash
uv run python -m compileall -q webscoper
uv run pytest --collect-only -q
uv run pytest -q
uv run python scripts/run_workflow_eval.py --cases tests/fixtures/langgraph_main_eval_cases.json --output-dir eval_results/langgraph_eval_local
uv run python scripts/run_workflow_eval.py --cases tests/fixtures/tool_gateway_eval_cases.json --output-dir eval_results/tool_gateway_eval_local
uv run python scripts/run_workflow_eval.py --cases tests/fixtures/langgraph_skill_eval_cases.json --output-dir eval_results/langgraph_skill_eval_local
cd apps/web && pnpm lint && pnpm build
```

## Safety

VaniScope does not bypass login, CAPTCHA, paywalls, or access controls. It does not enter real passwords, payment information, or PII. Public web access is disabled by default, and mutating or ambiguous actions must go through RiskGate and Approval.

## Cleanup Audit

The current architecture compaction audit is in `docs/architecture_cleanup_audit.md`.
