# VaniScope

[English](README.md)

VaniScope / Web-Scoper 是一个 Python 浏览器 Agent Runtime，用于本地和 fixture 驱动的网页任务执行。当前包含浏览器观察与 click intent、确定性和 LLM planner 模式、证据与报告 artifact、Reviewer 与 revise loop、FastAPI Task API、Risk Gate 审批暂停/恢复、Context Compaction、native / LangGraph workflow backend，以及 backend 行为回归评测。

Runtime 现在按职责拆成 `runtime/execution`、`runtime/artifacts`、`runtime/llm`、`runtime/prompt`、`runtime/review` 和 `runtime/safety`。旧 flat import 路径暂时保留为 compatibility layer。

`webscoper/workflows/langgraph_adapter.py` 仍然是 LangGraph workflow 的公开入口；内部编排模块位于 `webscoper/workflows/langgraph_backend/`。

Browser recovery 现在拆成 `browser/recovery/classifier`、`planner`、`strategies`、`executor` 和 `telemetry`；`browser/recovery/manager.py` 保持为公开 facade。

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

## 目录结构

```text
webscoper/
  browser/       # Browser Runtime：Playwright session、观察、定位、效果验证、恢复、风险信号
  runtime/       # Agent Runtime：execution、artifacts、LLM、prompt、review、safety 兼容层
  api/           # FastAPI Task API、异步任务、审批、SSE 事件流、artifact 访问
  eval/          # Browser / Planner / Reviewer / Workflow regression eval harness
  workflows/     # Native workflow 与 LangGraph backend 编排模块
  tools/         # Tool registry 与 browser tools
  schemas/       # 共享 Pydantic schema

scripts/
  run_task.py
  run_api.py
  run_browser_eval.py
  run_planner_eval.py
  run_reviewer_eval.py
  run_workflow_eval.py
  smoke_open_page.py

configs/
  llm.example.toml
  llm.local.toml  # 仅本地使用，已忽略

docs/
  compatibility_imports.md
  runtime_modules.md

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

Workflow regression eval 会在同一组本地任务 case 上对比 native 与 LangGraph workflow backend，不访问真实网络，也不调用真实 LLM。

```bash
uv run python scripts/run_workflow_eval.py \
  --cases tests/fixtures/workflow_eval_cases.json \
  --output-dir eval_results/workflow_eval_local
```
