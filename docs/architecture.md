# VaniScope Architecture

VaniScope / Web-Scoper is a LangGraph-based Browser Agent Runtime. It is built
around local, replayable browser tasks: observe a page, execute governed tool
calls, collect evidence, verify effects, review the final answer, and expose
every important step as artifacts.

The current release-candidate mainline is Python-first:

- Python Runtime: Browser Runtime, ToolGateway, evidence, review, approval,
  recovery, evals, and FastAPI
- LangGraph: the only workflow orchestration backend
- Playwright: browser execution against local fixtures and supported pages
- Next.js 16: local control console backed by FastAPI

There is no native workflow compatibility layer in the mainline.

## Positioning

VaniScope is not a generic web search assistant. It is a runtime and control
plane for browser-agent execution that emphasizes:

- deterministic local demos
- artifact replay
- risk governance
- evidence-backed reporting
- regression evals
- inspectable task state

The demo skills, `docs_research` and `github_issue_research`, are examples of
how domain tasks can sit on top of the same Browser Runtime and ToolGateway.
They do not introduce a separate workflow backend.

## Browser Runtime Reliability Model

Browser Runtime reliability is built as a loop:

1. Observe the page.
2. Resolve the intended target.
3. Execute an action only when the target is safe and available.
4. Verify the expected effect.
5. Recover from known local failure modes.
6. Persist trace, transcript, evidence, audit, and recovery artifacts.

The runtime treats browser execution as observable and replayable. A failed run
should still leave enough artifacts for debugging.

## Action Intent, Target Resolution, Effect Verification, Recovery

Action intent starts from a task-level click target such as `Quickstart` or
`Submit`. The planner emits tool calls; the runtime validates tool ordering and
arguments before execution.

Target resolution uses visible page information and intent hints to find the
best button, link, or control candidate. The runtime avoids force-clicking
disabled or unsafe controls.

Effect verification checks postconditions such as expected text appearing after
a click. A click that does not change the page as expected is not treated as a
success merely because the browser accepted it.

Recovery handles known local failure classes:

- target not found
- target covered by modal overlay
- postcondition failed
- target disabled
- login/password required
- CAPTCHA detected

Recovery plans and outcomes are written to `recovery.jsonl`.

## ToolGateway Governance

ToolGateway is the formal tool invocation boundary used by LangGraph tool
nodes. It is responsible for:

- resolving tool descriptors
- applying policy
- checking permission and risk level
- dispatching to providers
- creating approval requests
- blocking dangerous calls
- writing `tool_audit.jsonl`

Current providers include Browser Runtime and deterministic local/fake
MCP-shaped providers for tests. Real MCP server integration is intentionally
out of scope for this mainline.

## Evidence, Review, Approval Flow

Evidence is written as structured JSONL records with source URL, page title,
text, trace references, and metadata. Final reports cite evidence IDs.

Review checks that reports include evidence, avoid unsupported claims, and
satisfy expected task outcomes. Review writes `review.json` and
`review_summary.md`. Optional fake/real LLM review is controlled separately and
is not required for the default path.

Approval is triggered by risk decisions such as submit-style or sensitive
actions. The workflow pauses, writes `approvals.jsonl`, `pending.jsonl`, and
`risk_report.json`, and FastAPI exposes approval decision endpoints. Approved
calls can resume; rejected calls stop safely.

## Runtime Inspector And Artifact Replay

Runtime Inspector turns a run directory into a replayable debugging model. It
does not execute code, call the browser, access the network, or call an LLM.

It reads:

- `events.jsonl`
- `trace.jsonl`
- `transcript.jsonl`
- `tool_audit.jsonl`
- `llm_calls.jsonl`
- `recovery.jsonl`
- `approvals.jsonl`
- `pending.jsonl`
- `evidence.jsonl`
- `review.json`
- `final_report.md`
- prompt and context artifacts

It returns timeline items, summaries, evidence links, LLM summaries, approval
summaries, and artifact presentation metadata. The Next.js console uses this
metadata to separate user-facing views from Developer/Debug raw artifacts.

## FastAPI And Next.js Boundaries

FastAPI is the runtime API:

- `POST /tasks/async`
- `GET /tasks/{task_id}`
- `GET /tasks/{task_id}/events`
- `GET /tasks/{task_id}/artifacts`
- `GET /tasks/{task_id}/timeline`
- `GET /tasks/{task_id}/inspector`
- approval endpoints
- `GET /health`
- `GET /diagnostics`

Next.js is intentionally thin. It creates tasks, displays status, streams SSE
events, renders artifacts, submits approval decisions, and stores recent task
history in browser `localStorage`. It does not import Python runtime internals
and does not own runtime state.

## LLM Control

Real LLM use is controlled and not enabled by default because release-candidate
behavior must be deterministic, affordable, auditable, and runnable without
credentials. The default path uses deterministic or fake planner/reviewer
modes.

When real providers are used, they require explicit local configuration in
ignored files such as `configs/llm.local.toml`, audited budget checks, and
`llm_calls.jsonl` records. API keys are not written to artifacts.

## Deferred Go Control Plane

The Go control plane is deferred to a later branch because the current release
candidate is about stabilizing the Python runtime contract:

- task lifecycle
- browser execution
- governance
- artifact schema
- inspector/replay
- eval harness
- local console

Keeping Go out of this branch avoids mixing runtime stabilization with a
control-plane rewrite. It also gives the future Go layer a cleaner API and
artifact contract to wrap.
