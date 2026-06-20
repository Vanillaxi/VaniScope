# VaniScope

[English](README.md)

VaniScope / Web-Scoper 是一个本地可回放的 Browser Agent Runtime，使用
Python、FastAPI、LangGraph、Playwright、ToolGateway、证据化报告、审批工作流、
运行 artifact 回放、回归 eval 和 Next.js 控制台构建。

用于执行、审计和检查浏览器 agent 工作流的运行时。

## 边界

- LangGraph 是 workflow 编排层。
- Browser Runtime 使用 Playwright，默认面向本地 fixture 和受控页面。
- ToolGateway 是工具调用治理边界，负责 policy、risk、approval、provider dispatch
  和 `tool_audit.jsonl`。
- FastAPI 负责任务 API、事件流、artifact 读取、审批、resume 和 diagnostics。
- Next.js 是本地控制台，不是生产 SaaS 前端。
- 真实 LLM 必须通过本地配置显式启用；测试和 demo 默认不依赖真实 LLM。
- VaniScope 不会绕过登录、验证码、付费墙或访问控制，也不会输入真实敏感信息。

## 目录边界

```text
webscoper/
  api/           FastAPI Task API、审批、artifact、diagnostics、resume
  browser/       Playwright runtime、观察、目标解析、效果验证、readiness、recovery
  eval/          LangGraph workflow eval runner
  runtime/       执行循环、artifact、prompt、LLM、review、safety、inspector
  schemas/       Pydantic 数据契约
  skills/        docs_research 和 github_issue_research
  tools/         Tool registry 与 ToolGateway
  workflows/     LangGraph adapter、approval bridge、backend nodes

apps/web/        Next.js 本地控制台
scripts/         API、任务、workflow eval、browser smoke 入口
tests/           精简后的关键回归测试和本地 fixtures
```

## 核心模块

`webscoper/browser` 负责浏览器执行：`StatefulBrowserToolRuntime`、页面观察、
目标解析、效果验证、readiness、风险信号和 recovery。

`webscoper/runtime` 负责 LangGraph 之下的任务生命周期：prompt 构建、tool-call
规划和校验、artifact 写入、LLM 路由、review、审批安全和 Runtime Inspector 聚合。

`webscoper.workflows.LangGraphWorkflowAdapter` 是公开 workflow 入口，内部实现位于
`webscoper/workflows/langgraph_backend/`。

`webscoper/tools/gateway` 是正式工具调用边界。LangGraph 节点调用
`ToolGateway.invoke()`，由 gateway 判断工具调用是允许、阻止、等待审批，还是转发给
provider。

`webscoper/skills` 是任务层能力。默认 registry 只有 `docs_research` 和
`github_issue_research`；二者都使用本地 fixture，不访问真实 GitHub、外部网站或真实
MCP 服务。

## 本地运行

启动 API：

```bash
uv run python scripts/run_api.py
```

启动控制台：

```bash
cd apps/web
pnpm install
pnpm dev
```

访问：

```text
http://localhost:3000
```

默认 API：

```text
http://localhost:8000
```

健康检查：

```text
GET /health
GET /diagnostics
```

如果 API 地址不同，在 `apps/web/.env` 中设置：

```bash
NEXT_PUBLIC_VANISCOPE_API_BASE_URL=http://localhost:8000
```

## Demo 输入

浏览器任务：

```text
url: tests/fixtures/mock_site/basic.html
click: Quickstart
expect: pip install playwright
planner: deterministic
workspace: tests/fixtures/workspace
```

Docs Research：

```text
url: tests/fixtures/mock_site/docs_research.html
task_type: docs_research
skill_id: docs_research
query: How do I install and run VaniScope?
language: en
```

GitHub Issue Research：

```text
url: tests/fixtures/mock_site/github_issue_research.html
task_type: github_issue_research
skill_id: github_issue_research
query: Analyze whether this issue is worth doing and summarize difficulty, affected modules, and risks.
language: en
```

审批 demo：

```text
url: tests/fixtures/mock_site/risk_actions.html
click: Submit
expect: Submitted successfully
planner: deterministic
workspace: tests/fixtures/workspace
```

恢复 demo：

```text
url: tests/fixtures/mock_site/early_button_hydration.html
click: Quickstart
expect: pip install playwright
planner: deterministic
workspace: tests/fixtures/workspace
```

## 浏览器可靠性

VaniScope 不把 `domcontentloaded` 或 `networkidle` 当成唯一完成信号。真实页面可能有
hydration、skeleton、spinner、overlay、SPA 路由延迟或长轮询。

`PageReadinessDetector` 会采样轻量信号：

- document ready state
- URL/title/text 稳定性
- interactive element 数量稳定性
- spinner/skeleton/overlay 是否消失
- 目标是否可见、启用、稳定、未被遮挡
- soft network quiet

readiness 状态包括 `ready`、`loading`、`degraded_ready` 和 `timeout`。
`degraded_ready` 只表示页面足够用于安全观察或只读提取，不会绕过登录、验证码、
支付、安全或 PII 边界。

共享 mock site 只保留可复用页面：basic、hydration recovery、risk actions、
docs research 和 GitHub issue research。spinner、skeleton、overlay、SPA route delay、
disabled target、long-poll-like 等单测专属页面都放在 pytest 临时 HTML 中。

## Runtime Inspector

Runtime Inspector 从 run directory 读取已有 artifact，不重新执行任务，不访问网络，
也不调用真实 LLM。它聚合：

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

FastAPI 暴露：

```text
GET /tasks/{task_id}/timeline
GET /tasks/{task_id}/inspector
```

控制台使用这些接口展示 Timeline、Artifacts、Evidence、LLM / Prompt、Review 和
Approval。

## LLM 配置

默认路径是 deterministic 或 fake LLM。真实 provider 只通过本地配置开启：

```text
configs/llm.example.toml
configs/llm.local.toml
```

真实 provider 必须设置：

```toml
[router]
mode = "real"
```

LLM 调用会经过预算控制，并写入 `llm_calls.jsonl`。API key 不会写入 artifact。
dry-run 任务会生成 `prompt_preview.md`、`prompt_context.json` 和 `dry_run_result.json`，
然后在浏览器或 LLM 执行前停止。

## 测试和 Eval

运行 pytest：

```bash
uv run pytest -q
```

运行 workflow eval：

```bash
uv run python scripts/run_workflow_eval.py \
  --cases tests/fixtures/langgraph_main_eval_cases.json \
  --output-dir eval_results/langgraph_eval_local
```

运行 ToolGateway eval：

```bash
uv run python scripts/run_workflow_eval.py \
  --cases tests/fixtures/tool_gateway_eval_cases.json \
  --output-dir eval_results/tool_gateway_eval_local
```

运行 skill eval：

```bash
uv run python scripts/run_workflow_eval.py \
  --cases tests/fixtures/langgraph_skill_eval_cases.json \
  --output-dir eval_results/langgraph_skill_eval_local
```


## 常见 artifact

- `final_report.md`：最终报告。
- `evidence.jsonl`：证据条目。
- `review.json` / `review_summary.md`：报告审查结果。
- `trace.jsonl`：浏览器/runtime trace。
- `transcript.jsonl`：运行转录。
- `events.jsonl`：任务事件。
- `tool_audit.jsonl`：ToolGateway 审计。
- `recovery.jsonl`：恢复策略记录。
- `approvals.jsonl` / `pending.jsonl` / `risk_report.json`：审批相关 artifact。
- `workflow_state.json`：LangGraph workflow state 快照。

