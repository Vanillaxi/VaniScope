# VaniScope

[English](README.md)

VaniScope / Web-Scoper 的第一阶段是一个 Python 单机 Browser Runtime MVP。它只实现公开网页任务的浏览器执行底座，不包含 LLM、LangGraph、Go 后端、MCP、Reviewer 或 Web Research Skill。

当前能力：

- 打开公开 URL。
- 观察页面状态并抽取结构化 observation。
- 保存页面截图。
- 将 action / observation 写入 `trace.jsonl`。
- 初步检测高风险页面元素，例如 password、captcha、payment、login。
- 提供命令行 smoke script，用于打开网页并生成 trace。

## 阶段边界

这个 MVP 不会绕过登录、验证码或付费墙，也不会输入真实账号、密码、支付信息或身份证件。默认只用于公开网页和测试页面。

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
  schemas/       # TraceStep、PageObservation 等 Pydantic schema
  runtime/       # TraceRecorder 和 BrowserRuntime orchestration
  browser/       # Playwright session、observer、risk detection

scripts/
  smoke_open_page.py

traces/
  .gitkeep

tests/
  test_trace_recorder.py
```

## 后续扩展方向

当前模块边界为后续 TargetResolver、ActionContract、EffectVerifier、RecoveryManager 预留空间。第一阶段只负责浏览器会话、页面观察、风险信号和 trace 记录。
