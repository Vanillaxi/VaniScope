# Project Architecture Compaction Audit

Date: 2026-06-23

## Formal Mainline

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

## Directory Summary

```text
webscoper/api
  app.py, task_service.py, schemas.py, approvals.py, artifacts.py, resume.py,
  diagnostics.py, runner_factory.py, task_state.py

webscoper/browser
  session.py, actions.py, observer.py, readiness.py, risk.py, public_web.py,
  target.py, effects.py, tool_runtime.py, recovery/

webscoper/runtime
  execution/, llm/, prompt/, artifacts/, review/, persistence/, safety/,
  inspector/, control.py

webscoper/tools
  registry.py, gateway/

webscoper/workflows
  langgraph_approval.py, state.py, langgraph_backend/

webscoper/schemas
  task.py, tool.py, browser.py, agent.py, artifact.py, review.py, llm.py,
  runtime.py, workflow.py, eval.py

webscoper/skills
  base.py, registry.py, router.py, docs_research.py, github_issue_research.py

tests
  25 focused test files after compaction

scripts
  run_api.py, run_task.py, run_workflow_eval.py, run_public_web_smoke.py,
  run_real_llm_smoke.py

apps/web
  Next.js console with task, inspector, artifact, evidence, approval, eval views
```

## Module Status

| Area | Status | Notes |
| --- | --- | --- |
| `webscoper/api` | keep | Current FastAPI boundary. `api/schemas.py` remains API-shaped; domain schemas live in `webscoper/schemas`. |
| `webscoper/browser` | keep | Browser capability layer. It still contains the compatibility methods in `tool_runtime.py`; they are not first-class prompt tools. |
| `webscoper/browser/recovery` | merge | Recovery is useful but split across several small files. Keep for now because readiness/recovery tests still cover it. |
| `webscoper/runtime/execution` | merge | Core execution remains, but `handler.py` is still large. `planner.py` and validator now emit v2 tool ids. |
| `webscoper/runtime/llm` | keep | Current fake/real LLM path. `router.py` is large and has budget logic that may later be split. |
| `webscoper/runtime/prompt` | keep | Official prompt exposure path; compatibility wrappers are hidden here. |
| `webscoper/runtime/artifacts` | keep | Evidence, report, trace, transcript, compaction pipeline. |
| `webscoper/runtime/review` | keep | Deterministic and LLM review/revision path. |
| `webscoper/runtime/safety` | keep | Approval, pending approvals, RiskGate. |
| `webscoper/runtime/inspector` | keep | Timeline, graph, presentation, loader, schemas. |
| `webscoper/tools/gateway` | keep | Official tool invocation boundary. |
| `webscoper/tools/registry.py` | keep | Catalog source of truth; snapshot now excludes compatibility/disabled tools from core lists. |
| `webscoper/workflows/langgraph_backend` | keep | LangGraph-only workflow backend. |
| `webscoper/eval/workflow_eval.py` | keep | Current workflow eval runner. |
| `scripts` | keep | Old one-off smoke scripts removed. |
| `tests` | merge | Reduced from 39 test files to 25 high-value files. |
| `apps/web` | keep | Console retained; Tool Catalog now hides compatibility wrappers. |

## Legacy Scan

Commands used:

```bash
rg "browser_open_observe"
rg "browser_click_intent"
rg "native"
rg "run_browser_eval|run_planner_eval|run_reviewer_eval|run_langgraph_eval|run_phase39_smoke"
rg "planner_mode"
rg "fake-planner"
rg "compat|deprecated|TODO|legacy|old"
```

Findings:

| Pattern | Result |
| --- | --- |
| native workflow/backend/runner | Not present as an executable path. |
| old eval runners | Not present. |
| old eval modules | Not present; only `webscoper/eval/workflow_eval.py` remains. |
| `browser_open_observe` / `browser_click_intent` | Retained only as centralized compatibility wrapper ids in registry/provider/runtime compatibility methods and explicit prompt-exposure tests. |
| old planner path | Deterministic and fake LLM planner output migrated to v2 tool ids. |
| old prompt path | Prompt exposure hides compatibility wrappers. |
| old smoke scripts | Removed `scripts/smoke_open_page.py` and `scripts/smoke_click_intent.py`. |
| duplicate LLM config loaders | `runtime/llm/config.py` is the main config loader; diagnostics read the resolved router. |
| duplicate task state definitions | `api/schemas.py` still defines API response status literals while domain task/runtime state stays in `schemas/` and runtime context. |
| unused recovery files | Recovery files are still covered by readiness/recovery behavior and retained. |
| unused inspector files | Inspector files are still used by API/console and retained. |
| unused test fixtures | Fixture set is already compact and retained. |

## Deleted

Scripts:

```text
scripts/smoke_click_intent.py
scripts/smoke_open_page.py
```

Tests:

```text
tests/api/test_approvals.py
tests/api/test_async_tasks.py
tests/api/test_compaction_artifacts.py
tests/api/test_health.py
tests/api/test_revise_loop.py
tests/api/test_runtime_graph_api.py
tests/api/test_task_timeline_api.py
tests/api/test_tasks.py
tests/api/test_workflows.py
tests/browser/test_browser_recovery_runtime.py
tests/browser/test_recovery_manager.py
tests/eval/test_browser_benchmark_schema.py
tests/runtime/test_approvals_events.py
tests/tools/test_tool_gateway_policy.py
```

## Merged Or Compacted

- Root README and README_CN were reduced to entrypoint architecture, run/config/test commands, and safety boundaries.
- ToolGateway eval cases were compacted around Browser Tool Contract v2 calls.
- Deterministic planner and fake LLM planner now produce `browser_open`, `browser_observe`, `browser_click`, `browser_extract`, and `finish_task`.
- Plan validation now validates v2 ordering and required arguments.
- Tests were reduced to 25 files while retaining API, browser v2, public web, readiness/risk, LLM, runtime, skills, ToolGateway, and LangGraph coverage.

## Temporarily Retained

Compatibility wrappers:

```text
webscoper/tools/registry.py
webscoper/tools/gateway/providers.py
webscoper/browser/tool_runtime.py
webscoper/runtime/execution/tool_executor.py
```

Reason: existing external callers or saved artifacts may still reference the old tool ids. They are centralized, marked as `compatibility`, excluded from prompt/core snapshot exposure, and not used by the official planner/eval path.

Larger modules retained for a future pass:

```text
webscoper/runtime/execution/handler.py
webscoper/browser/tool_runtime.py
webscoper/runtime/llm/router.py
```

Reason: these files are large but still serve the formal product path. Splitting them safely should be a dedicated follow-up after this compatibility pruning.

## Decision Lists

Must delete:

- old smoke scripts
- old eval runners/modules if reintroduced
- native workflow paths if reintroduced
- tests that require old wrapper tool ids as first-class tools

Recommended delete:

- remaining compatibility wrappers after downstream callers and saved fixtures no longer need them
- `webscoper/schemas/eval.py` if future workflow eval no longer imports it

Recommended merge:

- `webscoper/browser/recovery/*` small files
- `webscoper/runtime/execution/handler.py` into smaller orchestration/report/persistence units
- duplicate status literals between API responses and domain schemas

Keep:

- LangGraph backend
- ToolGateway
- Browser Tool Contract v2
- Evidence/report/review artifacts
- Runtime Inspector graph/timeline APIs
- SQLite metadata persistence
- workflow eval cases under `tests/fixtures/*eval_cases.json`
