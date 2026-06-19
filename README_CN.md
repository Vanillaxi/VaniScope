# VaniScope

[English](README.md)

VaniScope / Web-Scoper 是一个基于 LangGraph 的浏览器 Agent Runtime，用于本地和 fixture 驱动的网页任务执行。当前包含浏览器观察与 click intent、确定性和 LLM planner 模式、证据与报告 artifact、Reviewer 与 revise loop、FastAPI Task API、Risk Gate 审批暂停/恢复、Context Compaction、LangGraph workflow backend、workflow 行为回归评测，以及 Next.js 16 控制台。

Runtime 现在按职责拆成 `runtime/execution`、`runtime/artifacts`、`runtime/llm`、`runtime/prompt`、`runtime/review` 和 `runtime/safety`。runtime 根目录的旧兼容 re-export 已移除，项目代码直接导入具体子包路径。

`webscoper/workflows/langgraph_adapter.py` 仍然是 LangGraph workflow 的公开入口；内部编排模块位于 `webscoper/workflows/langgraph_backend/`。LangGraph 是唯一任务编排层。

`webscoper/tools/gateway/` 是正式工具调用入口。LangGraph tool node 调用 `ToolGateway.invoke()`，由它统一执行 policy、risk/approval 决策、provider dispatch，并写入 `tool_audit.jsonl`。Browser Runtime 作为 ToolGateway provider 接入，`FakeMCPToolProvider` 提供 deterministic 的本地 MCP 形态模拟工具。

Browser recovery 现在拆成 `browser/recovery/classifier`、`planner`、`strategies`、`executor` 和 `telemetry`；`browser/recovery/manager.py` 保持为公开 facade。

`webscoper/skills/` 是 LangGraph 上层 skill 层。默认 registry 当前包含
`docs_research`，它通过现有 Browser Runtime 和 ToolGateway 路径读取本地文档页，
并输出带证据的 `final_report.md`、`review.json` 和 `skill_result.json`。

## 阶段边界

VaniScope 不会绕过登录、验证码或付费墙，也不会输入真实账号、密码、支付信息或身份证件。高风险动作会被阻止，或要求本地审批后才继续执行。

## 运行 Smoke

```bash
uv run python scripts/smoke_open_page.py https://example.com
uv run python scripts/smoke_open_page.py https://example.com --headed
```

每次运行会创建：

- `traces/<run_id>/trace.jsonl`
- `traces/<run_id>/step_001.png`

终端会输出 `run_id`、最终 URL、页面标题、截图路径、交互元素数量、风险信号数量和 trace 路径。

## 运行测试

```bash
uv run pytest
```

默认 pytest 保留 workflow 的少量 smoke case。需要完整 recovery / approval 回归矩阵时，运行下面的显式 workflow eval 命令。

## 控制台

Next.js 16 控制台位于 `apps/web`，只对接 FastAPI Task API。它支持完整跑通本地 LangGraph browser task，通过 SSE 查看实时事件，查看 artifacts，处理审批，查看 evidence / review / report 输出，以及打开本地 eval 命令辅助页面。

The Next.js 16 control console lives in `apps/web` and talks only to the FastAPI Task API. It can create and complete local LangGraph browser tasks, stream task events over SSE, inspect artifacts, handle approvals, view evidence/review/report outputs, and show the local eval command helper.

启动 API：

Start the API:

```bash
uv run python scripts/run_api.py
```

配置并启动前端：

Configure and start the console:

```bash
cd apps/web
pnpm install
pnpm dev
```

访问 `http://localhost:3000`。控制台读取：

Open `http://localhost:3000`. The console reads:

```bash
NEXT_PUBLIC_VANISCOPE_API_BASE_URL=http://localhost:8000
```

如果 API 地址不同，可以基于 `apps/web/.env.example` 创建本地 `.env`。

Copy `apps/web/.env.example` to a local `.env` if you need a different API base URL.

完整链路 demo / Full-stack demo:

```text
docs/demo_next_console.md
```

## 目录结构

```text
webscoper/
  browser/       # Browser Runtime：Playwright session、观察、定位、效果验证、恢复、风险信号
  runtime/       # Agent Runtime：execution、artifacts、LLM、prompt、review、safety
  skills/        # Skill 定义、registry、确定性 router、docs_research skill
  api/           # FastAPI Task API、异步任务、审批、SSE 事件流、artifact 访问
  eval/          # Browser / Planner / Reviewer / Workflow regression eval harness
  workflows/     # LangGraph backend 编排模块
  tools/         # Tool registry、browser tools 与 ToolGateway providers
  schemas/       # 共享 Pydantic schema

apps/
  web/           # 对接 FastAPI Task API 的 Next.js 16 控制台

scripts/
  run_task.py
  run_api.py
  run_browser_eval.py
  run_planner_eval.py
  run_reviewer_eval.py
  run_workflow_eval.py
  run_langgraph_eval.py
  smoke_open_page.py

configs/
  llm.example.toml
  llm.local.toml  # 仅本地使用，已忽略

docs/
  runtime_modules.md
  skills.md

runs/
  .gitkeep

traces/
  .gitkeep

eval_results/
  .gitkeep

tests/
  api/
  browser/
  eval/
  llm/
  runtime/
  workflows/
  fixtures/
```

## 配置

`configs/llm.example.toml` 是可提交的配置模板。本地 provider 配置放在 `configs/llm.local.toml`；本地配置文件和生成的 run/eval artifact 会被 git 忽略。

## Workflow Eval

LangGraph workflow eval 会运行本地任务 case，不访问真实网络，也不调用真实 LLM。主 fixture 覆盖：

- workflow case：status、artifacts、review、evidence 和 compaction
- recovery case：lazy control、modal overlay、no-effect retry、ambiguous target、disabled control、login/password block 和 captcha block
- approval case：RiskGate approval-required、task pause、approved resume、rejected stop、delete blocked，以及 approvals/pending/events/risk report 审计 artifact

```bash
uv run python scripts/run_workflow_eval.py \
  --cases tests/fixtures/langgraph_main_eval_cases.json \
  --output-dir eval_results/langgraph_eval_local
```

Runner 会在输出目录写入 `score.json` 和 `report.md`。`score.json` 包含总量、通过/失败数量、recovery/approval 通过数量和 LangGraph expectation failure。

Tool Gateway eval 以 LangGraph 为主，覆盖 browser provider、本地 deterministic MCP 形态工具、approval、blocked 和 audit 行为：

```bash
uv run python scripts/run_workflow_eval.py \
  --cases tests/fixtures/tool_gateway_eval_cases.json \
  --output-dir eval_results/tool_gateway_eval_local
```

Skill eval 使用本地 docs fixture 验证 `docs_research` MVP：

```bash
uv run python scripts/run_langgraph_eval.py \
  --cases tests/fixtures/langgraph_skill_eval_cases.json \
  --output-dir eval_results/langgraph_skill_eval_local
```
