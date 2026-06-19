# Runtime Module Map

This document is a lightweight boundary map for `webscoper/runtime/`. The runtime package is split by responsibility into execution, artifacts, LLM, prompt, review, and safety subpackages. Project code imports these package paths directly.

The skill layer lives outside runtime in `webscoper/skills/`. Skills are
LangGraph task capabilities, not a separate workflow backend. They select
instructions, plans, and skill metadata while the workflow still executes
through Browser Runtime and ToolGateway. The default registry currently
contains `docs_research` and `github_issue_research`.

## Execution-Related Modules

- `execution/handler.py` owns the high-level agent execution handler: context creation, prompt building, planning, validation, tool-loop execution, and artifact finalization.
- `execution/loop.py` runs validated tool-call plans through `LocalToolExecutor`, records transcript events, emits task events, and stores evidence.
- `execution/tool_executor.py` bridges tool calls to the local tool registry and browser runtime while enforcing risk checks and approval pause behavior.
- `execution/runner.py` is the CLI-facing orchestration layer for the LangGraph workflow.
- `execution/context.py`, `execution/events.py`, `execution/state.py`, and `execution/results.py` hold run context, task events, state payload helpers, and tool-result evidence helpers.
- `execution/planner.py`, `execution/plan_validator.py`, and `execution/tool_call_parser.py` support deterministic plans, plan validation, and LLM tool-call parsing.

## Tool Gateway

`webscoper/tools/gateway/` is the formal tool invocation boundary for the LangGraph workflow. LangGraph tool nodes call `ToolGateway.invoke()`, which resolves descriptors, applies `ToolGatewayPolicy`, handles RiskGate/approval decisions, dispatches to a provider, and appends `tool_audit.jsonl`.

Gateway providers currently include:

- `BrowserToolProvider`, an adapter over `StatefulBrowserToolRuntime`.
- `LocalToolProvider`, a small local deterministic provider for direct gateway tests.
- `FakeMCPToolProvider`, deterministic MCP-shaped local tools (`fake_mcp_echo`, `fake_mcp_get_time`, `fake_mcp_fetch_doc`) plus disabled/dangerous fixtures for policy tests.

`tool_audit.jsonl` records timestamp, task ID, workflow backend, tool name, provider type, permission, risk level, decision, status, error type, duration, and approval ID. The audit path intentionally avoids raw secrets and is written under the run directory.

## LLM-Related Modules

- `llm/client.py` defines fake and OpenAI-compatible LLM clients.
- `llm/config.py` loads environment/file-backed provider configuration.
- `llm/router.py` resolves configured providers into concrete clients.
- `llm/planner.py` builds plans from LLM tool-call responses and handles repair attempts.
- `llm/reviewer.py` provides LLM-backed review integration for the revise loop.

## Artifact-Related Modules

- `artifacts/trace.py` writes `trace.jsonl`.
- `artifacts/transcript.py` writes `transcript.jsonl`.
- `artifacts/evidence.py` manages `evidence.jsonl` and evidence context packs.
- `artifacts/report.py` builds `final_report.md`.
- `artifacts/compaction.py` creates `compact_context.json` and `compact_summary.md`.
- Skill-aware artifact persistence also writes `skill_result.json` for selected
  skills such as `docs_research` and `github_issue_research`.

## Review And Revision Modules

- `review/reviewer.py` performs deterministic report review and summary markdown generation.
- `review/revision.py` plans and applies deterministic report revisions.
- `review/revise_loop.py` coordinates deterministic and optional fake/real LLM review-revision passes.

## Safety And Approval Modules

- `safety/risk_gate.py` maps tool calls and page observations to allow / approval / block decisions.
- `safety/approvals.py` stores approval requests and decisions.
- `safety/pending.py` stores pending tool calls for approval resume.

## Prompt And Context Modules

- `context.py` defines runtime context snapshots and run state.
- `prompt/builder.py` builds planner prompts from task context, tool schemas, reminders, compacted context, and AGENTS.md instructions.
- Skill instructions are injected by `prompt/builder.py` before tool
  instructions when LangGraph routes a task to a skill.
- `prompt/agents_md.py` loads workspace instructions.
- `prompt/reminders.py` stores runtime reminders.

## Workflow Integration Boundary

LangGraph is the only workflow orchestration backend. `webscoper/runtime/` stays focused on core runtime capabilities beneath LangGraph: Browser Runtime, Tool Runtime, Evidence, Review, Approval, Eval, and Audit.

`webscoper/workflows/langgraph_adapter.py` is the public LangGraph entry point. LangGraph orchestration internals live under `webscoper/workflows/langgraph_backend/`, split into graph construction, node implementations, resume handling, artifact/state writing, and workflow event helpers.

Workflow eval lives in `webscoper/eval/workflow_eval.py` and is LangGraph-only. The eval runner records status, artifacts, review, evidence, recovery, approval, risk, audit, and event behavior without changing runtime semantics.

The workflow eval schema supports `case_type` values of `workflow`, `recovery`, `approval`, and `tool_gateway`. Recovery cases assert expected recovery strategies and error types from `recovery.jsonl`. Approval cases assert RiskGate decisions, approval-required/task-paused events, approve/reject resume outcomes, and persisted `approvals.jsonl`, `pending.jsonl`, `events.jsonl`, and `risk_report.json` artifacts. Tool Gateway cases assert LangGraph gateway provider, decision, status, risk level, workflow backend, and audit behavior. `tests/fixtures/langgraph_main_eval_cases.json` is the main LangGraph matrix; `tests/fixtures/tool_gateway_eval_cases.json` is the gateway matrix. Eval cases are guarded to use local fixture URLs and non-real planner/reviewer modes, so pytest and eval runs do not access real network targets or real LLM providers.

`tests/fixtures/langgraph_skill_eval_cases.json` covers `docs_research` with
the local docs page and `github_issue_research` with
`tests/fixtures/mock_site/github_issue_research.html`. It checks
`final_report.md`, `evidence.jsonl`, `review.json`, `skill_result.json`,
`tool_audit.jsonl`, affected modules, difficulty, contribution value, and skill
status without real network or real LLM calls.

## Control Console Boundary

`apps/web` contains the Next.js 16 control console for the LangGraph-based Browser Agent Runtime. The console is intentionally a thin FastAPI client: it creates tasks through `/tasks/async`, reads task status from `/tasks/{task_id}`, streams `/tasks/{task_id}/events`, loads allowlisted artifacts through the artifact endpoints, and submits approval decisions through the approval endpoints.

The console can complete the local LangGraph demo path end to end: create a fixture-backed task, observe execution over SSE, open final report / review / evidence / audit artifacts, and resolve approval-required pauses from the UI. It does not import Python runtime internals, does not store data, and does not add authentication. Browser access to the local API is enabled through FastAPI CORS for `http://localhost:3000` by default, with `VANISCOPE_CORS_ORIGINS` available for local overrides.

`docs/demo_next_console.md` documents the manual full-stack smoke path. The project remains LangGraph-only.

## Browser Recovery Boundary

`webscoper/browser/recovery/` is split by recovery responsibility:

- `classifier.py` classifies browser, action, and effect failures.
- `planner.py` maps failure types to recovery plans.
- `strategies.py` implements concrete recovery actions.
- `executor.py` executes recovery plans and attempts.
- `telemetry.py` records recovery trace, transcript events, evidence, and `recovery.jsonl`.
- `manager.py` remains the public facade.
