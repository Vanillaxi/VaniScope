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

Open `http://localhost:3000`, then go to `新建任务`.

Use the demo case:

```text
url: tests/fixtures/mock_site/basic.html
click: Quickstart
expect: pip install playwright
planner: deterministic
workspace: tests/fixtures/workspace
```

The form has a `填入 demo case` button that restores these values.

Submit the form. The console should redirect to:

```text
/tasks/{task_id}
```

## 4. Verify Task Detail

On the task detail page, verify:

- task status is visible
- current phase / step is visible when events provide it
- SSE events appear in `事件流`
- `任务产物` lists generated artifacts
- `final_report.md` appears when the task completes
- `review.json`, `evidence.jsonl`, `events.jsonl`, and `tool_audit.jsonl` can be opened from the artifact viewer

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
- Frontend health card OK
- Create task OK
- Task detail page OK
- SSE events visible
- Artifacts visible
- `final_report.md` visible
- `review.json` visible
- `evidence.jsonl` visible
- `tool_audit.jsonl` visible
- Approval decision works for the approval fixture
