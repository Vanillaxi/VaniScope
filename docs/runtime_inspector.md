# Runtime Inspector

Runtime Inspector turns a task run directory into a replayable debugging view.
It does not execute the task again, call a real LLM, access the network, or
read outside the selected `runs/task_*` directory. It only aggregates existing
artifacts.

## What It Reads

The inspector reads these artifacts when present:

- `events.jsonl`
- `trace.jsonl`
- `tool_audit.jsonl`
- `llm_calls.jsonl`
- `recovery.jsonl`
- `approvals.jsonl`
- `evidence.jsonl`
- `review.json`
- `prompt_preview.md`
- `prompt_context.json`
- `final_report.md`

Missing artifacts are treated as empty inputs, so incomplete or failed runs can
still be inspected.

## Timeline Aggregation

`RuntimeTimelineBuilder` merges runtime artifacts into one deterministic
timeline. Items are sorted by timestamp when available and by stable fallback
order otherwise. Each item includes:

- category: workflow, browser, tool, llm, recovery, approval, evidence, review, or report
- title and summary
- status
- step/tool/evidence references
- artifact references and raw payload

Tool audit rows become tool timeline items. Browser trace rows become browser
items. LLM audit rows expose provider, model, mode, purpose, status, and budget
decision. Recovery and approval rows are shown in their own categories.
Evidence rows link back to report sections when `final_report.md` references an
evidence id.

## Backend API

FastAPI exposes two read-only endpoints:

```text
GET /tasks/{task_id}/timeline
GET /tasks/{task_id}/inspector
```

`/timeline` returns task id, summary, and timeline items.

`/inspector` returns task status, artifact names, timeline summary, evidence
links, review summary, LLM summary, and approval summary.

Both endpoints read directly from run artifacts. There is no database and no
runtime mutation.

## Console UI

The Next.js task detail page now has Runtime Inspector tabs:

- Timeline
- Artifacts
- Evidence
- LLM / Prompt
- Review
- Approval

The Timeline tab is the unified replay view. Evidence shows evidence ids,
source URL/title, text preview, and report/review links. LLM / Prompt shows
`prompt_preview.md`, `prompt_context.json`, `llm_calls.jsonl` when present, and
explicitly states when there are no real LLM calls. Review shows `review.json`,
issue counts, unsupported claims, and revision artifacts when present.

This makes Browser Agent Runtime behavior observable: prompts, tool calls,
browser observations, risk decisions, approvals, evidence, reports, reviews,
and LLM budget decisions can be inspected after a run.
