# VaniScope

[English](README.md)

VaniScope 是一个 local-first Browser Agent Runtime，用于执行、审计和回放浏览器 agent 工作流。当前正式主线已经收束为：

```text
Next.js Console
-> FastAPI
-> LangGraph Workflow
-> Auto Explore Planner
-> ToolGateway
-> Browser Tool Contract v2
-> Lazy Tool / Lazy Skill Loader
-> Browser Runtime / Playwright
-> Evidence / Report / Review
-> Inspector / Graph / Timeline
-> SQLite metadata persistence
```

默认路径是本地 fixture 上的 deterministic / fake LLM 执行。真实 LLM provider 和公网访问都必须通过本地配置显式开启。

## 架构

```text
webscoper/
  api/        FastAPI task、artifact、approval、resume、diagnostics API
  browser/    Playwright session、v2 browser action、observation、readiness、recovery
  eval/       Workflow eval runner
  runtime/    execution、prompt、LLM、safety、artifact、review、inspector、persistence
  schemas/    Domain contracts
  skills/     docs_research 和 github_issue_research
  tools/      Tool registry 和 ToolGateway
  workflows/  LangGraph adapter 和 backend

apps/web/     Next.js 本地控制台
scripts/      当前 run/eval/smoke 入口
tests/        高价值回归测试
```

`ToolGateway` 是正式工具调用边界。LangGraph 节点调用 gateway，由它负责 policy、risk check、approval、provider dispatch 和 `tool_audit.jsonl`。

`webscoper/browser` 只负责真实浏览器能力：打开、观察、点击、安全 fixture 输入/选择、滚动、等待、提取、截图、readiness 和 recovery。它不负责 workflow planning、prompt 或 report 生成。

## Browser Tools

Browser Tool Contract v2 是唯一一等工具层：

```text
browser_open
browser_observe
browser_click
browser_type
browser_select
browser_scroll
browser_wait
browser_extract
browser_screenshot
ask_human
finish_task
```

LLM 只能选择结构化 action 和自然语言 `target_hint`，不能输出 selector、XPath、Playwright code、JavaScript 或 raw DOM handle。RiskGate、PublicWebPolicy、Approval、Evidence、Trace、Timeline 和 Graph 都仍在执行路径上。

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

访问 `http://localhost:3000`。默认 API 是 `http://localhost:8000`；如需覆盖，在 `apps/web/.env` 设置 `NEXT_PUBLIC_VANISCOPE_API_BASE_URL`。

## 配置

Runtime 配置：

```bash
cp configs/runtime.example.toml configs/runtime.local.toml
```

LLM 配置：

```bash
cp configs/llm.example.toml configs/llm.local.toml
```

不要提交本地配置、数据库、runs、traces、downloads、browser state、`.env`、`.next`、`node_modules`、缓存或 eval output。

公网模式：

```text
local        默认；只允许 local fixture、file://、localhost
public_safe  只允许 allow-list 命中的公网域名
public_open  仅用于本地手动探索的公网 HTTP/HTTPS 放开模式
```

真实 LLM 模式和公网模式是两个独立开关，开启一个不会自动开启另一个。

## Demo 输入

Auto explore：

```text
mode: auto_explore
url: tests/fixtures/mock_site/basic.html
goal: Summarize the visible page information and collect evidence.
planner: fake_llm
workspace: tests/fixtures/workspace
```

确定性点击：

```text
mode: guided
url: tests/fixtures/mock_site/basic.html
click: Quickstart
expect: pip install playwright
planner: deterministic
workspace: tests/fixtures/workspace
```

Docs research：

```text
url: tests/fixtures/mock_site/docs_research.html
task_type: docs_research
skill_id: docs_research
query: How do I install and run VaniScope?
language: en
```

GitHub issue research：

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

## 当前脚本

```bash
uv run python scripts/run_api.py
uv run python scripts/run_task.py --url tests/fixtures/mock_site/basic.html --planner deterministic
uv run python scripts/run_workflow_eval.py --cases tests/fixtures/langgraph_main_eval_cases.json --output-dir eval_results/langgraph_eval_local
uv run python scripts/run_public_web_smoke.py --config configs/runtime.local.toml --cases tests/fixtures/public_web_smoke_cases.example.json
uv run python scripts/run_real_llm_smoke.py --cases tests/fixtures/real_llm_smoke_cases.example.json --output-dir eval_results/real_llm_smoke_local
```

## 测试和 Eval

```bash
uv run python -m compileall -q webscoper
uv run pytest --collect-only -q
uv run pytest -q
uv run python scripts/run_workflow_eval.py --cases tests/fixtures/langgraph_main_eval_cases.json --output-dir eval_results/langgraph_eval_local
uv run python scripts/run_workflow_eval.py --cases tests/fixtures/tool_gateway_eval_cases.json --output-dir eval_results/tool_gateway_eval_local
uv run python scripts/run_workflow_eval.py --cases tests/fixtures/langgraph_skill_eval_cases.json --output-dir eval_results/langgraph_skill_eval_local
cd apps/web && pnpm lint && pnpm build
```

## 安全边界

VaniScope 不绕过登录、验证码、付费墙或访问控制；不输入真实密码、支付信息或 PII。公网访问默认关闭，变更性或有歧义的动作必须经过 RiskGate 和 Approval。

## 清理审计

当前架构压缩审计文档在 `docs/architecture_cleanup_audit.md`。
