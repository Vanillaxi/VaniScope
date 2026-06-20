# VaniScope

VaniScope / Web-Scoper is a LangGraph-based Browser Agent Runtime for local,
replayable browser-agent tasks. It combines Python, FastAPI, LangGraph,
Playwright, ToolGateway governance, evidence-backed reporting, human approval
workflows, runtime artifact replay, regression evals, and a Next.js 16 control
console.

VaniScope is not a generic web search assistant. It is a runtime for executing
and inspecting browser-agent workflows with strong local demos, deterministic
regression coverage, and auditable artifacts.

## What It Does

VaniScope runs browser tasks through a LangGraph workflow, executes governed
browser/tool calls, verifies effects, records evidence, reviews the final
report, pauses for risky actions, and exposes the whole run through a Runtime
Inspector.

The current Python mainline is release-candidate focused:

- LangGraph is the only workflow backend.
- Browser execution uses Playwright and local fixtures by default.
- Real LLM providers are supported only through explicit local config and are
  not enabled by default.
- Demo skills use local fixture pages and do not call real GitHub, real MCP
  servers, or external web targets.
- Go control-plane work is intentionally deferred to a later branch.

## Architecture

```text
Next.js Console  ->  FastAPI Task API  ->  LangGraph Workflow
                                              |
                                              v
                                      ToolGateway Policy
                                              |
                                              v
                                  Browser Runtime / Providers
                                              |
                                              v
                            Evidence, Review, Approval, Artifacts
                                              |
                                              v
                                  Runtime Inspector / Replay
```

Core boundaries:

- `webscoper/workflows/`: LangGraph workflow adapter and backend nodes.
- `webscoper/browser/`: Playwright browser runtime, observation, target
  resolution, effect verification, risk signals, and recovery.
- `webscoper/tools/gateway/`: tool governance, provider dispatch, approval
  decisions, and `tool_audit.jsonl`.
- `webscoper/runtime/`: execution, artifacts, prompt context, LLM routing,
  review, safety, and inspector logic.
- `webscoper/api/`: FastAPI task API, SSE event stream, artifacts, approvals,
  diagnostics, timeline, and inspector endpoints.
- `apps/web/`: Next.js 16 local console.

See [docs/architecture.md](docs/architecture.md) for the detailed architecture.

## Core Features

- Browser Runtime: observe pages, resolve click intent, execute actions, verify
  expected effects, and recover from known browser failure modes.
- LangGraph Workflow: one orchestration path for browser tasks, approvals,
  recovery, skill execution, and artifact finalization.
- ToolGateway: a governed tool boundary with policy, risk classification,
  approval pause, provider dispatch, and audit records.
- Evidence and Review: writes `evidence.jsonl`, builds `final_report.md`, and
  checks claims through deterministic review in `review.json`.
- Approval Workflow: risky submit/delete/password/CAPTCHA-like actions are
  approved, rejected, or blocked with persisted artifacts.
- Runtime Inspector: replays run directories into timeline, report, evidence,
  review, tools, LLM, and debug views.
- Next.js Console: local task workspace with API health, skill launchers, task
  detail tabs, user-friendly artifact rendering, and Developer raw views.
- Diagnostics: `GET /diagnostics` reports API status, LangGraph backend,
  artifact directory, default fake LLM status, registered skills, browser
  readiness, and redacted config state.

## Demo Scenarios

The default demos are local and deterministic:

1. Browser Task Demo: click `Quickstart` in
   `tests/fixtures/mock_site/basic.html` and verify `pip install playwright`.
2. Docs Research Demo: run `docs_research` on
   `tests/fixtures/mock_site/docs_research.html`.
3. GitHub Issue Research Demo: run `github_issue_research` on
   `tests/fixtures/mock_site/github_issue_research.html`; this uses a mock
   issue fixture only.
4. Approval Demo: submit action on `tests/fixtures/mock_site/risk_actions.html`,
   pause, approve or reject, and inspect approval artifacts.
5. Recovery Demo: run local lazy/modal/no-effect/ambiguous fixtures and inspect
   `recovery.jsonl`.

See [docs/demo_playbook.md](docs/demo_playbook.md) for exact inputs, expected
artifacts, console views, common failures, and debugging paths.

## Local Run

Install Python dependencies with the project environment you already use for
`uv`.

Start FastAPI from the repository root:

```bash
uv run python scripts/run_api.py
```

Start the Next.js console:

```bash
cd apps/web
pnpm install
pnpm dev
```

Open:

```text
http://localhost:3000
```

Default API base URL:

```text
http://localhost:8000
```

Check runtime readiness:

```text
GET http://localhost:8000/health
GET http://localhost:8000/diagnostics
```

If the API uses a different base URL, create a local `apps/web/.env` from
`apps/web/.env.example` and set:

```bash
NEXT_PUBLIC_VANISCOPE_API_BASE_URL=http://localhost:8000
```

Do not commit local `.env`, `configs/*.local.toml`, `configs/llm.toml`,
generated `runs/`, `traces/`, `eval_results/`, `.next/`, `node_modules/`, or
cache files.

## Eval And Regression

Run all tests:

```bash
uv run pytest -q
```

Run the deterministic Phase 39 smoke suite:

```bash
uv run python scripts/run_phase39_smoke.py \
  --output-dir eval_results/phase39_demo_smoke
```

Run LangGraph skill evals:

```bash
uv run python scripts/run_langgraph_eval.py \
  --cases tests/fixtures/langgraph_skill_eval_cases.json \
  --output-dir eval_results/langgraph_skill_eval_local
```

Run the main workflow eval matrix:

```bash
uv run python scripts/run_workflow_eval.py \
  --cases tests/fixtures/langgraph_main_eval_cases.json \
  --output-dir eval_results/langgraph_eval_local
```

Run ToolGateway evals:

```bash
uv run python scripts/run_workflow_eval.py \
  --cases tests/fixtures/tool_gateway_eval_cases.json \
  --output-dir eval_results/tool_gateway_eval_local
```

See [docs/eval_report.md](docs/eval_report.md) for the release-candidate eval
coverage.

## LLM Configuration

The default path is deterministic or fake-LLM. Real LLM providers are controlled
and must be explicitly configured in ignored local files such as
`configs/llm.local.toml`.

Use `configs/llm.example.toml` as the template. Real providers require
`router.mode = "real"` and an OpenAI-compatible provider with credentials. API
keys are never written to artifacts.

See [docs/llm_readiness.md](docs/llm_readiness.md).

## Project Layout

```text
webscoper/
  api/           # FastAPI task API, SSE, approvals, artifacts, diagnostics
  browser/       # Playwright Browser Runtime, recovery, risk, effects
  eval/          # Regression eval harnesses
  runtime/       # Execution, artifacts, inspector, LLM, prompt, review, safety
  schemas/       # Shared Pydantic models
  skills/        # docs_research and github_issue_research demo skills
  tools/         # Tool registry and ToolGateway
  workflows/     # LangGraph workflow backend

apps/web/        # Next.js 16 control console
scripts/         # API, task, eval, smoke runners
docs/            # Architecture, eval, demo, inspector, LLM docs
tests/           # API, browser, runtime, eval, skills, workflows, tools
```

## Limitations

- No real network access is required or assumed for demos/evals.
- The GitHub Issue Research demo uses local mock issue HTML, not GitHub API.
- Real LLM providers are not enabled by default.
- The runtime does not bypass login, CAPTCHA, paywalls, or access control.
- There is no production database, authentication, multi-user tenancy, or hosted
  deployment package.
- The Next.js console is a local control console, not a production SaaS
  frontend.
- Real MCP server integration and Go control-plane work are intentionally
  deferred.

## Roadmap

Near-term:

- Keep Python runtime APIs and artifacts stable.
- Expand deterministic eval coverage for artifact and inspector regressions.
- Improve demo polish and error diagnostics.
- Document artifact schemas and task lifecycle more formally.

Later branches:

- Go control plane wrapping the stabilized Python runtime contract.
- Optional real MCP server adapters.
- Optional production deployment and persistence model.
- Broader browser/runtime compatibility testing.
