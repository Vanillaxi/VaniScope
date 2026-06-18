# Runtime Module Map

This document is a lightweight boundary map for `webscoper/runtime/`. Phase 23 does not split the runtime package; it records the current shape so later refactors can move deliberately.

## Execution-Related Modules

- `execution.py` owns the high-level agent execution handler: context creation, prompt building, planning, validation, tool-loop execution, and artifact finalization.
- `execution_loop.py` runs validated tool-call plans through `LocalToolExecutor`, records transcript events, emits task events, and stores evidence.
- `tool_executor.py` bridges tool calls to the local tool registry and browser runtime while enforcing risk checks and approval pause behavior.
- `task_runner.py` is the CLI-facing orchestration layer for native and LangGraph workflow selection.
- `planner.py`, `plan_validator.py`, and `tool_call_parser.py` support deterministic plans, plan validation, and LLM tool-call parsing.

## LLM-Related Modules

- `llm_client.py` defines fake and OpenAI-compatible LLM clients.
- `llm_config.py` loads environment/file-backed provider configuration.
- `llm_router.py` resolves configured providers into concrete clients.
- `llm_planner.py` builds plans from LLM tool-call responses and handles repair attempts.
- `llm_reviewer.py` provides LLM-backed review integration for the revise loop.

## Artifact-Related Modules

- `trace.py` writes `trace.jsonl`.
- `transcript.py` writes `transcript.jsonl`.
- `evidence.py` manages `evidence.jsonl` and evidence context packs.
- `report.py` builds `final_report.md`.
- `compaction.py` creates `compact_context.json` and `compact_summary.md`.

## Review And Revision Modules

- `reviewer.py` performs deterministic report review and summary markdown generation.
- `revision.py` plans and applies deterministic report revisions.
- `revise_loop.py` coordinates deterministic and optional fake/real LLM review-revision passes.

## Safety And Approval Modules

- `risk_gate.py` maps tool calls and page observations to allow / approval / block decisions.
- `approvals.py` stores approval requests and decisions.
- `pending.py` stores pending tool calls for approval resume.

## Prompt And Context Modules

- `context.py` defines runtime context snapshots and run state.
- `prompt_builder.py` builds planner prompts from task context, tool schemas, reminders, compacted context, and AGENTS.md instructions.
- `agents_md.py` loads workspace instructions.
- `reminders.py` stores runtime reminders.

## Workflow Integration Boundary

`webscoper/runtime/` stays workflow-backend neutral where possible. Native execution is driven directly by `WebAgentExecutionHandler`; LangGraph integration lives in `webscoper/workflows/` and calls runtime APIs rather than replacing the browser runtime, tool registry, risk gate, approval store, or execution artifacts.
