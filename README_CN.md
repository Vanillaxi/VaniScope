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
- 公网访问默认关闭；本地 fixture、`file://`、localhost 和 `127.0.0.1` 仍是默认运行面。
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
mode: auto_explore
url: tests/fixtures/mock_site/basic.html
goal: Summarize the visible page information and collect evidence.
planner: fake_llm
workspace: tests/fixtures/workspace
```

确定性浏览器调试任务：

```text
mode: guided
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

## 会话持久化与 Auto Explore

VaniScope 使用本地 SQLite 保存 conversation 和 task metadata。默认路径是
`data/vaniscope.db`，可以通过 `configs/runtime.local.toml` 中的
`[persistence].sqlite_path` 或 `VANISCOPE_DB_PATH` 配置。SQLite 只保存
conversation、message、task metadata、artifact 路径/大小和 approval metadata；
trace、screenshot、prompt、report 等大型 artifact 仍保存在 `runs/task_xxx/`。

FastAPI 包含：

```text
POST /conversations
GET /conversations
GET /conversations/{conversation_id}
GET /conversations/{conversation_id}/messages
POST /tasks
```

Browser Task 现在支持 `mode: auto_explore`，用户只需要输入 URL 和自然语言目标。
`guided` 模式仍保留，用于 deterministic demo 和显式 `click` / `expect` 调试。
`skill` 模式继续用于 `docs_research`、`github_issue_research` 等注册 skill。

auto-explore 循环中，LLM 只能选择结构化 action intent：

```text
observe
click_intent
extract
ask_human
finish
```

LLM 不允许直接选择 CSS selector、XPath、JavaScript 或 DOM handle。它只能给
`target_hint`；真正的目标解析和执行仍由 Browser Runtime 完成，并继续受
ToolGateway、PublicWebPolicy、RiskGate、Approval、PageReadinessDetector、
TargetResolver、EffectVerifier、RecoveryManager、EvidenceStore 和 task budget
约束。

网页内容是不可信 evidence，不是系统指令。页面里的 prompt injection 文本，例如
要求忽略规则或点击破坏性按钮，仍必须符合用户目标和安全策略，才可能被执行。

fake / deterministic 路径仍是测试和 CI 默认路径。真实 LLM 只能通过
`configs/llm.local.toml` 等本地配置显式启用；不要提交真实 key。pytest 和
workflow eval 不依赖真实公网或真实 LLM。

## Web Runtime 模式

VaniScope 默认 local-first，但真实公网访问是正式的本地 runtime mode。pytest、
workflow eval、CI 和仓库默认配置都不会启用公网访问。

复制并编辑示例配置：

```bash
cp configs/runtime.example.toml configs/runtime.local.toml
```

不要提交 `configs/runtime.local.toml` 或任何 `configs/*.local.toml`。

模式：

- `local`：默认模式。允许本地 fixture、`file://`、localhost、`127.0.0.1`
  和 `::1`；阻断公网 URL。
- `public_safe`：只允许 `allowed_domains` 命中的公网 HTTP/HTTPS 域名。
- `public_open`：允许任意公网 HTTP/HTTPS 域名，通常配合 `allowed_domains = ["*"]`，
  仅用于本地手动探索。

`public_safe` 示例：

```toml
[web]
mode = "public_safe"
public_network_enabled = true
allowed_domains = ["github.com", "playwright.dev", "docs.python.org", "arxiv.org"]
max_pages_per_task = 3
request_delay_ms = 250
navigation_timeout_ms = 12000
```

`browser_open_observe` 导航前会先分类 URL：

- 本地 fixture / `file://`：默认允许
- localhost / `127.0.0.1` / `::1`：默认允许
- 公网 `http` / `https`：`local` 阻断，`public_safe` 按域名 allow-list，
  `public_open` 放开公网域名
- 私有或内部网络地址 / hostname：阻止
- `javascript:`、`data:` 等不支持 scheme：阻止

所有模式下安全边界都仍然生效：不绕过登录、验证码、付费墙或访问控制，不输入真实
密码、支付或 PII 字段，不自动执行删除、发布、付款等 destructive actions。

## 公网 Smoke

公网 smoke 是手动、非确定性的 smoke，不是 benchmark，也不属于默认 CI。

手动 smoke case 示例位于：

```text
tests/fixtures/public_web_smoke_cases.example.json
```

手动运行：

```bash
uv run python scripts/run_public_web_smoke.py \
  --config configs/runtime.local.toml \
  --cases tests/fixtures/public_web_smoke_cases.example.json
```

runner 会在 `runs/` 下写入 `summary.json` 和任务 artifact。断言是软断言：页面打开、
title 存在、可见文本非空、任务成功时产物存在。公网 smoke 是非确定性的，不是 benchmark。

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
default_provider = "openai_compatible"

[providers.openai_compatible]
type = "openai_compatible"
base_url = "https://api.openai.com/v1"
api_key = "YOUR_API_KEY_HERE"
model = "gpt-4.1-mini"
timeout_seconds = 30
```

public web mode 和 real LLM mode 是两个独立开关：开启其中一个不会自动开启另一个。
真实公网探索需要同时配置 `configs/runtime.local.toml` 的公网访问，以及
`configs/llm.local.toml` 中的 `router.mode = "real"`。

LLM 调用会经过 Budget Gate v2，并写入 `llm_calls.jsonl`、
`prompt_budget_estimate.json` 和 `budget_decisions.jsonl`。API key 不会写入
artifact、diagnostics 或 smoke summary。action validation 失败会写入
`action_validation.json`。

预算控制不是简单 hard fail，而是分层处理：

- soft token / cost limit 只发出 `budget_warning`，任务继续执行。
- approval token / cost limit 会创建 Human-in-the-loop 的 `llm_budget` approval，
  并把任务暂停为 `waiting_for_approval`。
- 用户可以选择 continue once、continue for the task、continue with compaction、
  stop and summarize 或 cancel。
- provider context 与 task hard limit 仍然必须遵守，只能通过 compaction、减少上下文
  或 partial report 安全停止。

用户控制面同时暴露在 Console 和 API：

```text
POST /tasks/{task_id}/pause
POST /tasks/{task_id}/resume
POST /tasks/{task_id}/cancel
POST /tasks/{task_id}/stop-and-summarize
```

Pause、cancel 和 stop 请求都是协作式执行。runner 会在 LLM call、tool call、
browser action、recovery 和 report generation 前后的安全 checkpoint 检查控制状态。
`stop-and-summarize` 会用已收集 evidence 生成 partial report；如果还没有 evidence，
会生成 minimal report，说明任务在收集到足够证据前已停止。

手动 real LLM smoke 是 opt-in，不属于 pytest 或 CI：

```bash
uv run python scripts/run_real_llm_smoke.py \
  --cases tests/fixtures/real_llm_smoke_cases.example.json \
  --output-dir eval_results/real_llm_smoke_local
```

smoke runner 使用软断言，输出 task status、final URL/title、action count、
LLM call count、artifact 存在情况、failure reason 和 run_dir。

dry-run 任务会生成 `prompt_preview.md`、`prompt_context.json` 和 `dry_run_result.json`，
然后在浏览器或 LLM 执行前停止。

## Browser Tool Contract v2

VaniScope 的浏览器工具层升级为 Browser Tool Contract v2。LLM 只能选择 action intent，不能输出 selector、XPath、Playwright code、JavaScript 或 raw DOM 操作。实际执行仍然必须经过 ToolGateway、RiskGate、Approval、Evidence、Trace、Timeline 和 Graph。

| Tool | 用途 | 风险 / 说明 |
| --- | --- | --- |
| `browser_open` | 在 task 浏览器 session 中打开 URL。 | read-only，必须经过 PublicWebPolicy。 |
| `browser_observe` | 返回面向 LLM 的 observation：可见文本、main content、accessibility summary、交互元素、readiness、risk signals、可选截图 evidence。 | 默认不调用 vision model。 |
| `browser_click` | 用自然语言 `target_hint` 点击，并验证 expected effect。 | TargetResolver 选元素；高风险点击走 RiskGate / Approval。 |
| `browser_type` | 向目标输入安全 mock 文本。 | 默认 local fixture 优先；public web typing 和敏感值默认 block。 |
| `browser_select` | 按 option text/value 选择。 | local fixture 优先；public web 可能变更状态的 select 需要人工确认。 |
| `browser_scroll` | 上下滚动并观察结果。 | read-only，有每 task scroll 限制。 |
| `browser_wait` | 等待 readiness、URL 变化、内容出现、network quiet 或 fixed delay。 | LLM 不能直接 sleep，必须调用工具。 |
| `browser_extract` | 从当前可见页面提取 evidence-backed summary。 | 保留 source URL 和 evidence id。 |
| `browser_screenshot` | 显式截图并作为 first-class evidence。 | JSONL 不写 base64。 |
| `ask_human` | 暂停等待人工输入/决策。 | 登录、验证码、支付、删除、发布、真实提交和不安全歧义必须走这里或 block。 |
| `finish_task` | 不做新浏览器动作，基于 evidence 结束并生成报告。 | 浏览器中立的最终步骤。 |

兼容 wrapper 仍然保留：`browser_open_observe` 维持旧的 open+observe 形态，`browser_click_intent` 维持旧 click-intent 入口。新的 prompt 和 Tool Catalog 优先展示 v2 名称。

浏览器 session 默认是 task scope：`browser_session_id`、`browser_context_id`、`page_id` 会写入 workflow/session metadata。默认不保存 cookies / localStorage，不跨 public web task 复用登录态，也不会绕过登录、验证码或访问控制。storage_state 只作为显式本地 opt-in 预留。

预留工具 `browser_upload_file`、`browser_download`、`browser_drag` 默认 disabled。本阶段不开放 public web 上传/下载/拖拽；未来启用时必须使用受控目录和人工确认。

Eval schema 已预留 BrowserGym / WebArena 风格本地 benchmark 字段，但本阶段不接真实 BrowserGym 或 WebArena benchmark。

## 面试演示路径

这条路径用于展示 VaniScope 是真实 Web Agent runtime，而不是普通日志列表。

示例任务：

```text
URL: https://github.com/Vanillaxi
Goal: 总结这个用户的开源经历、主要仓库、技术方向和活跃情况。
```

演示顺序：

1. 启动 API 和 Console，新建任务，选择 `public_safe` 公网访问、`auto_explore` 和 `real_llm`。
2. 先打开 `Timeline`。展示 `planner_started`、`llm_call_finished`、`llm_action_proposed`、`tool_call_started`、浏览器 open/navigation、readiness wait、extract/click、evidence 和 report 事件。
3. 打开 `Graph`。展示链路：`Task -> LLM -> ToolGateway -> Browser -> Readiness -> Evidence -> Report`。
4. 点击 `browser_open` / `browser_open_observe` 节点。展示 before/after URL、耗时、截图 evidence、readiness confidence，以及 DOM complete、skeleton/spinner/overlay absent、layout stable、soft network quiet 等信号。
5. 点击 LLM 节点。展示 provider/model、proposed action、validation result，以及是否发生 repair；同时说明 payload 里没有 API key。
6. 点击 `Evidence`。展示页面截图 evidence、文本 evidence、source URL、page title，以及 report 使用的 evidence id。
7. 在任务运行中点击 `Stop and summarize`。展示状态从 `stop_requested` 到 `succeeded_partial`，然后打开基于当前 evidence 生成的 partial report。
8. 打开 `Graph`，展示 `User Stop -> Partial Report` 链路。如果出现预算审批，展示 `Budget Approval` 节点和 Human-in-the-loop 卡片。
9. 打开 `Report`。说明最终或 partial 报告基于 `evidence.jsonl` 生成，不依赖隐藏的浏览器状态。
10. 如果任务失败，回到 `Graph` 或 `Timeline`，检查 recovery、failure screenshot、error node 和相关 trace payload。

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
- `graph.json`：用于离线复盘的执行图。
- `observation.json`：最新 rich browser observation。
- `tool_audit.jsonl`：ToolGateway 审计。
- `recovery.jsonl`：恢复策略记录。
- `approvals.jsonl` / `pending.jsonl` / `risk_report.json`：审批相关 artifact。
- `workflow_state.json`：LangGraph workflow state 快照。
