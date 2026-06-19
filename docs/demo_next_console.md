# Next.js Console Demo

This demo runs the VaniScope Next.js 16 control console against the local FastAPI Task API and LangGraph Browser Agent Runtime. It uses only repository fixtures: no real network target, no real LLM, no Go backend, and no real MCP server.

## 1. Start FastAPI

From the repository root:

```bash
uv run python scripts/run_api.py
```

The API should be available at:

```text
http://localhost:8000
```

Health check:

```text
GET /health
```

## 2. Start Next.js

In another terminal:

```bash
cd apps/web
pnpm dev
```

The console should be available at:

```text
http://localhost:3000
```

If the API is not on `http://localhost:8000`, create a local `apps/web/.env` from `apps/web/.env.example`:

```bash
NEXT_PUBLIC_VANISCOPE_API_BASE_URL=http://localhost:8000
```

## 3. Create The Demo Task

Open `http://localhost:3000`. The first screen is a task workspace with skill
cards, API health, and a recent-task preview. The sidebar contains `+ New Task`,
skill shortcuts, Recent Tasks, language switching, and API health.

Click a skill card or sidebar shortcut:

```text
/tasks/new?skill=browser_task
/tasks/new?skill=docs_research
/tasks/new?skill=github_issue_research
```

Each skill shows only its relevant fields.

Use the demo case:

```text
url: tests/fixtures/mock_site/basic.html
click: Quickstart
expect: pip install playwright
planner: deterministic
workspace: tests/fixtures/workspace
```

The Browser Task form has a `Quickstart click demo` preset that restores these
values.

For the skill demo, use the Docs Research card or sidebar shortcut and choose
`Install docs demo`:

```text
task_type: docs_research
skill_id: docs_research
url: tests/fixtures/mock_site/docs_research.html
query: How do I install and run VaniScope?
language: en
```

The Chinese preset uses:

```text
query: 如何安装并运行 VaniScope？
language: zh
```

For the GitHub issue skill demo, use the GitHub Issue Research card or sidebar
shortcut and choose `Issue value analysis demo`:

```text
task_type: github_issue_research
skill_id: github_issue_research
url: tests/fixtures/mock_site/github_issue_research.html
query: Analyze whether this issue is worth doing and summarize difficulty, affected modules, and risks.
language: en
```

The Chinese GitHub issue preset uses:

```text
query: 分析这个 issue 是否值得做，并总结难度、影响模块和风险。
language: zh
```

Submit the form. The console should redirect to:

```text
/tasks/{task_id}
```

The created task is added to sidebar Recent Tasks via browser `localStorage`.
Opening a task detail page updates `last_opened_at` and the latest known status.

## 4. Verify Task Detail

On the task detail page, verify:

- task status is visible
- current phase / step is visible when events provide it
- SSE events appear in `事件流`
- `任务产物` lists generated artifacts
- `final_report.md` appears when the task completes
- `review.json`, `evidence.jsonl`, `events.jsonl`, and `tool_audit.jsonl` can be opened from the artifact viewer
- docs research tasks show `skill_id`, `task_type`, and `skill_status`
- GitHub issue research tasks show `skill_id`, `task_type`, `difficulty`, and
  `recommendation`
- docs research tasks include `skill_result.json`
- `prompt_preview.md` and `prompt_context.json` appear after prompt build
- `llm_calls.jsonl` appears when fake/mock/real LLM planning is used

The artifact viewer formats JSON and JSONL for readability and truncates very large content to keep the page responsive.

## 5. Approval Demo

Use a local approval fixture that triggers a submit-style action, such as:

```text
url: tests/fixtures/mock_site/risk_actions.html
click: Submit
expect: Submitted
planner: deterministic
workspace: tests/fixtures/workspace
```

When the runtime emits `approval_required`, the task pauses and the `审批` panel should show:

- approval id
- risk level
- tool name
- reason
- requested action
- approve / reject controls

Click `批准` to resume the task, or `拒绝` to stop it. The task detail page should refresh status, events, and approvals after the decision.

## Manual Smoke Checklist

- Backend health OK
- Sidebar API health OK
- Sidebar skill shortcuts OK
- Sidebar Recent Tasks OK after task creation
- Create task OK
- Task detail page OK
- SSE events visible
- Artifacts visible
- `final_report.md` visible
- `review.json` visible
- `evidence.jsonl` visible
- `tool_audit.jsonl` visible
- `skill_result.json` visible for the Docs Research Demo
- `skill_result.json` visible for the GitHub Issue Demo
- Approval decision works for the approval fixture
