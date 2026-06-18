# Runtime Module Map

This document is a lightweight boundary map for `webscoper/runtime/`. The runtime package is now split by responsibility into execution, artifact, LLM, prompt, review, and safety subpackages. Old flat runtime import paths remain as a compatibility layer; project-internal code should prefer the package paths below.

## Execution-Related Modules

- `execution/handler.py` owns the high-level agent execution handler: context creation, prompt building, planning, validation, tool-loop execution, and artifact finalization.
- `execution/loop.py` runs validated tool-call plans through `LocalToolExecutor`, records transcript events, emits task events, and stores evidence.
- `execution/tool_executor.py` bridges tool calls to the local tool registry and browser runtime while enforcing risk checks and approval pause behavior.
- `task_runner.py` is the CLI-facing orchestration layer for native and LangGraph workflow selection.
- `execution/planner.py`, `execution/plan_validator.py`, and `execution/tool_call_parser.py` support deterministic plans, plan validation, and LLM tool-call parsing.

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
- `prompt/agents_md.py` loads workspace instructions.
- `prompt/reminders.py` stores runtime reminders.

## Compatibility Imports

Flat modules such as `webscoper.runtime.evidence`, `webscoper.runtime.llm_client`, and `webscoper.runtime.tool_executor` are retained as one-line compatibility re-exports. See `docs/compatibility_imports.md` for the legacy-to-new path map.

## Workflow Integration Boundary

`webscoper/runtime/` stays workflow-backend neutral where possible. Native execution is driven directly by `WebAgentExecutionHandler`; LangGraph integration lives in `webscoper/workflows/` and calls runtime APIs rather than replacing the browser runtime, tool registry, risk gate, approval store, or execution artifacts.

`webscoper/workflows/langgraph_adapter.py` is kept as the public compatibility entry. LangGraph orchestration internals live under `webscoper/workflows/langgraph_backend/`, split into graph construction, node implementations, resume handling, artifact/state writing, and workflow event helpers.
