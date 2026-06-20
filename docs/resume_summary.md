# Resume Summary

## 中文简历版本

VaniScope / Web-Scoper 是一个基于 LangGraph 的 Browser Agent Runtime，使用
Python、FastAPI、Playwright、LangGraph 和 Next.js 16 构建，重点解决浏览器
Agent 的任务编排、工具治理、证据追踪、人工审批、运行时可观测性和回归评测。

- 设计并实现 FastAPI Task API 与 SSE 事件流，支持异步任务创建、状态查询、artifact 读取、审批决策和本地控制台联动。
- 构建 ToolGateway 工具治理层，统一处理工具描述、权限策略、风险分级、审批暂停、provider dispatch 和 `tool_audit.jsonl` 审计。
- 实现证据与报告链路：浏览器观测和工具结果写入 `evidence.jsonl`，最终报告引用 evidence id，并通过 deterministic reviewer 产出 `review.json`。
- 实现风险审批工作流：高风险 submit/delete/password/CAPTCHA 等行为进入 approval/block 路径，支持 pending tool call 持久化、批准恢复和拒绝终止。
- 构建 Runtime Inspector，将 `trace.jsonl`、`events.jsonl`、`tool_audit.jsonl`、`llm_calls.jsonl`、`recovery.jsonl`、`review.json` 等 artifacts 聚合成可 replay 的 timeline 和用户友好视图。
- 建立 LangGraph 回归评测体系，覆盖 Browser Runtime、recovery、approval、ToolGateway、docs_research、github_issue_research 和 artifact/inspector 验证，默认不依赖真实网络和真实 LLM。

## English GitHub / Portfolio Version

VaniScope / Web-Scoper is a LangGraph-based Browser Agent Runtime built with
Python, FastAPI, Playwright, LangGraph, and a Next.js 16 console. It focuses on
browser-agent orchestration, governed tool execution, evidence-backed reporting,
human approval workflows, artifact replay, and deterministic regression evals.

- Built a FastAPI task API with async execution, SSE event streaming, artifact access, approval decisions, timeline/inspector endpoints, and diagnostics.
- Designed ToolGateway as the governed tool boundary for LangGraph nodes, covering policy checks, risk classification, approval pauses, provider dispatch, and JSONL audit trails.
- Implemented evidence-backed reporting and deterministic review: browser observations and tool results become `evidence.jsonl`, final reports cite evidence IDs, and `review.json` captures unsupported claims and quality score.
- Added a risk/approval workflow for sensitive browser actions, including persisted pending tool calls, approval resume, rejection handling, and risk artifacts.
- Created Runtime Inspector to replay task runs from artifacts such as trace, events, tool audit, LLM calls, recovery, approvals, evidence, review, and final reports.
- Built a deterministic eval harness covering Browser Runtime recovery, approval flows, ToolGateway behavior, demo skills, artifact existence, and inspector/timeline availability without real network or real LLM dependencies.
