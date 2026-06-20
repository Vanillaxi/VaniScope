# VaniScope Demo Playbook

This playbook is for local demos of the LangGraph-only VaniScope / Web-Scoper
runtime. All scenarios use repository fixtures, deterministic or fake planner
mode, local artifacts, and the FastAPI + Next.js console. They do not require
real network access, real LLM credentials, a Go control plane, or a real MCP
server.

## Before You Demo

Start the API:

```bash
uv run python scripts/run_api.py
```

Start the console:

```bash
cd apps/web
pnpm dev
```

Open:

```text
http://localhost:3000
```

Useful probes:

```text
GET http://localhost:8000/health
GET http://localhost:8000/diagnostics
```

## Browser Task Demo

Input:

```text
skill: Browser Task
url: tests/fixtures/mock_site/basic.html
click: Quickstart
expect: pip install playwright
planner: deterministic
workspace: tests/fixtures/workspace
```

Expected behavior:

The runtime opens the local fixture, observes the page, clicks the Quickstart
target, verifies that the expected text appears, writes evidence, builds a final
report, and runs deterministic review.

Expected artifacts:

- `final_report.md`
- `evidence.jsonl`
- `review.json`
- `review_summary.md`
- `trace.jsonl`
- `transcript.jsonl`
- `events.jsonl`
- `tool_audit.jsonl`
- `prompt_preview.md`
- `prompt_context.json`
- `timeline.json`

Where to view it in the Next.js console:

- Overview: status, evidence count, tool calls, review status, LLM mode
- Timeline: workflow, browser, tool, evidence, review, and report events
- Report: user-friendly report view with raw markdown in Developer raw
- Evidence: evidence cards
- Review: review summary
- Tools: ToolGateway audit table
- Debug: trace, transcript, events, prompt context, and raw artifacts

Common failure causes:

- FastAPI is not running on `http://localhost:8000`
- Playwright browser binaries are missing
- The fixture path was changed or typed incorrectly
- `runs/` is not writable

Debugging path:

1. Open `/diagnostics` and check artifact directory and browser readiness.
2. In the console, open Timeline and find the last non-success item.
3. Open Debug and inspect `trace.jsonl`, `events.jsonl`, and `tool_audit.jsonl`.
4. If no artifacts exist, restart the API and retry the task.

## Docs Research Demo

Input:

```text
skill: Docs Research
task_type: docs_research
skill_id: docs_research
url: tests/fixtures/mock_site/docs_research.html
query: How do I install and run VaniScope?
language: en
planner: deterministic
workspace: tests/fixtures/workspace
```

Expected behavior:

The docs research skill reads the local docs fixture through the Browser Runtime
and ToolGateway, extracts relevant evidence, writes `skill_result.json`, builds
an evidence-backed final report, and runs deterministic review.

Expected artifacts:

- `final_report.md`
- `evidence.jsonl`
- `review.json`
- `review_summary.md`
- `skill_result.json`
- `trace.jsonl`
- `events.jsonl`
- `tool_audit.jsonl`
- `prompt_preview.md`
- `prompt_context.json`

Where to view it in the Next.js console:

- Overview: skill, task type, status, evidence count, review status
- Report: summarized answer to the docs question
- Evidence: quoted source snippets from the docs fixture
- Review: unsupported claim count and score
- Debug: `skill_result.json`, prompt artifacts, and raw trace

Common failure causes:

- The task was created as `browser_task` instead of `docs_research`
- `skill_id` was omitted when using manual API input
- The query is empty or unrelated to the fixture content
- The fixture page cannot be opened locally

Debugging path:

1. Check the task card for `task_type=docs_research` and `skill_id=docs_research`.
2. Open Debug and inspect `skill_result.json`.
3. Open Evidence and confirm the expected docs snippets were collected.
4. Use `/diagnostics` to confirm registered skills include `docs_research`.

## GitHub Issue Research Demo

Input:

```text
skill: GitHub Issue Research
task_type: github_issue_research
skill_id: github_issue_research
url: tests/fixtures/mock_site/github_issue_research.html
query: Analyze whether this issue is worth doing and summarize difficulty, affected modules, and risks.
language: en
planner: deterministic
workspace: tests/fixtures/workspace
```

Expected behavior:

The GitHub issue research skill reads the local mock issue fixture only. It does
not call GitHub or any network API. It summarizes difficulty, affected modules,
risks, and recommendation, then writes skill and review artifacts.

Expected artifacts:

- `final_report.md`
- `evidence.jsonl`
- `review.json`
- `review_summary.md`
- `skill_result.json`
- `trace.jsonl`
- `events.jsonl`
- `tool_audit.jsonl`
- `prompt_preview.md`
- `prompt_context.json`

Where to view it in the Next.js console:

- Overview: skill metadata, status, evidence count, recommendation
- Report: issue analysis
- Evidence: issue title, body, labels, acceptance details, and risk snippets
- Review: score and unsupported claims
- Debug: `skill_result.json`, raw trace, and prompt context

Common failure causes:

- Using a real GitHub URL instead of the local mock fixture
- Creating the task with the wrong skill
- Query omits the desired issue evaluation dimensions
- Local fixture content no longer matches test expectations

Debugging path:

1. Confirm the URL is `tests/fixtures/mock_site/github_issue_research.html`.
2. Confirm `/diagnostics` lists `github_issue_research`.
3. Open `skill_result.json` in Debug and verify difficulty and recommendation.
4. Open `evidence.jsonl` and confirm issue evidence was collected.

## Approval Demo

Input:

```text
skill: Browser Task
url: tests/fixtures/mock_site/risk_actions.html
click: Submit
expect: Submitted successfully
planner: deterministic
workspace: tests/fixtures/workspace
```

Expected behavior:

RiskGate marks the submit-style action as requiring approval. The LangGraph
workflow pauses, writes approval artifacts, and the console shows an approval
panel. Approving resumes the task; rejecting stops it.

Expected artifacts:

- `approvals.jsonl`
- `pending.jsonl`
- `risk_report.json`
- `events.jsonl`
- `tool_audit.jsonl`
- `trace.jsonl`
- `transcript.jsonl`
- `final_report.md` after successful approval and resume

Where to view it in the Next.js console:

- Overview: approval count and status
- Timeline: `approval_required`, `task_paused`, and resume events
- Approval panel: approve/reject controls
- Tools: approval-required ToolGateway decision
- Debug: `approvals.jsonl`, `pending.jsonl`, and `risk_report.json`

Common failure causes:

- The selected click target is not the risky Submit action
- The task already finished before the approval panel refreshed
- Approval artifacts are present but the task page is stale
- The browser fixture changed its visible button text

Debugging path:

1. Refresh the task detail page.
2. Open Tools and confirm a call has `decision=approval_required`.
3. Open Debug and inspect `approvals.jsonl` and `pending.jsonl`.
4. After approving or rejecting, check Timeline for resume or rejection events.

## Recovery Demo

Input:

```text
skill: Browser Task
url: tests/fixtures/mock_site/lazy_button.html
click: Quickstart
expect: pip install playwright
planner: deterministic
workspace: tests/fixtures/workspace
```

Expected behavior:

The first action path encounters a recoverable browser state. Recovery telemetry
records the attempted strategy, the runtime re-observes or retries as needed,
then proceeds when the expected content is available.

Expected artifacts:

- `recovery.jsonl`
- `trace.jsonl`
- `events.jsonl`
- `tool_audit.jsonl`
- `evidence.jsonl`
- `final_report.md`
- `review.json`

Where to view it in the Next.js console:

- Overview: recovery attempts count
- Timeline: recovery started/attempt/finished events
- Report: final result after recovery
- Evidence: post-recovery content
- Debug: raw `recovery.jsonl` and trace

Common failure causes:

- `repair_attempts` is left at `0` for a case that needs recovery
- The expected text does not match the fixture
- The fixture is changed so the lazy content never appears
- Playwright/browser readiness is missing

Debugging path:

1. Open Overview and check recovery attempt count.
2. Open Timeline and filter mentally for recovery events.
3. Open Debug and inspect `recovery.jsonl` next to `trace.jsonl`.
4. Run the workflow eval matrix if the behavior looks regressed:

```bash
uv run python scripts/run_workflow_eval.py \
  --cases tests/fixtures/langgraph_main_eval_cases.json \
  --output-dir eval_results/langgraph_eval_local
```
