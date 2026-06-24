import type { Language } from "@/lib/i18n";
import type { RuntimeGraphNode, RuntimeTimelineItem } from "@/lib/types";

export type LocaleCode = "zh-CN" | "en-US";

export function localeCode(language: Language): LocaleCode {
  return language === "zh" ? "zh-CN" : "en-US";
}

export function statusLabel(status?: string | null, language: Language = "zh") {
  if (!status) return language === "zh" ? "未知" : "Unknown";
  return (language === "zh" ? ZH_STATUS : EN_STATUS)[status] ?? status;
}

export function categoryLabel(category: string, language: Language) {
  return (language === "zh" ? ZH_CATEGORY : EN_CATEGORY)[category] ?? category;
}

export function eventDisplay(item: RuntimeTimelineItem, language: Language) {
  const labels = language === "zh" ? ZH_EVENT : EN_EVENT;
  const exact = labels[item.kind];
  const title = exact?.title ?? fallbackEventTitle(item, language);
  const description = exact?.description ?? fallbackEventDescription(item, language);
  return {
    title,
    description,
    status: statusLabel(item.status, language),
    category: categoryLabel(item.category, language),
  };
}

export function graphNodeDisplay(node: RuntimeGraphNode, language: Language) {
  const type = categoryLabel(node.type, language);
  const status = statusLabel(node.status, language);
  const tool =
    typeof node.metadata.tool_name === "string"
      ? node.metadata.tool_name
      : typeof node.metadata.tool_id === "string"
        ? node.metadata.tool_id
        : "";
  const key = graphNodeKey(node);
  const title = graphNodeTitle(key, node, language);
  const responsibility = graphNodeResponsibility(key, node, language);
  const label = tool
    ? language === "zh"
      ? `${title}：${tool}`
      : `${title}: ${tool}`
    : title;
  return { label, responsibility, status, type };
}

function fallbackEventTitle(item: RuntimeTimelineItem, language: Language) {
  if (item.category === "tool" && item.tool_name) {
    return language === "zh" ? `工具调用：${item.tool_name}` : `Tool call: ${item.tool_name}`;
  }
  if (item.category === "llm") return language === "zh" ? "LLM 调用" : "LLM call";
  if (item.category === "report") return language === "zh" ? "报告已生成" : "Report generated";
  if (item.category === "evidence") return language === "zh" ? "证据已采集" : "Evidence collected";
  return language === "zh" ? "运行事件" : item.title;
}

function fallbackEventDescription(item: RuntimeTimelineItem, language: Language) {
  if (language === "en") return item.summary ?? "";
  if (item.category === "error") return "任务遇到错误；原始错误信息可在详情或 Debug 中查看。";
  if (item.category === "tool") return "工具调用已记录；工具 ID 和原始参数保留在详情中。";
  if (item.category === "evidence") return "系统已保存页面证据，可在证据面板查看。";
  if (item.category === "report") return "系统已根据采集到的证据生成报告。";
  return "查看详情了解该事件的原始 payload。";
}

const ZH_STATUS: Record<string, string> = {
  success: "成功",
  succeeded: "成功",
  succeeded_partial: "部分成功",
  failed: "失败",
  error: "错误",
  running: "运行中",
  pending: "等待中",
  blocked: "已阻塞",
  waiting_for_approval: "等待审批",
  requires_approval: "等待审批",
  approval_required: "等待审批",
  paused: "已暂停",
  canceled: "已取消",
  rejected: "已拒绝",
  warning: "警告",
  skipped: "已跳过",
  degraded: "降级",
  generated: "已生成",
  collected: "已采集",
  passed: "已通过",
};

const EN_STATUS: Record<string, string> = {
  success: "Succeeded",
  succeeded: "Succeeded",
  succeeded_partial: "Partially succeeded",
  failed: "Failed",
  error: "Error",
  running: "Running",
  pending: "Pending",
  blocked: "Blocked",
  waiting_for_approval: "Waiting for approval",
  requires_approval: "Waiting for approval",
  approval_required: "Waiting for approval",
  paused: "Paused",
  canceled: "Canceled",
  rejected: "Rejected",
  warning: "Warning",
  skipped: "Skipped",
  degraded: "Degraded",
  generated: "Generated",
  collected: "Collected",
  passed: "Passed",
};

const ZH_CATEGORY: Record<string, string> = {
  workflow: "工作流",
  control: "控制",
  llm: "LLM",
  tool: "工具",
  browser: "浏览器",
  readiness: "就绪检查",
  verification: "效果验证",
  evidence: "证据",
  recovery: "恢复",
  approval: "审批",
  error: "错误",
  review: "审查",
  report: "报告",
  budget: "预算",
  planner: "规划器",
  verifier: "验证器",
  task: "任务",
};

const EN_CATEGORY: Record<string, string> = {
  workflow: "Workflow",
  control: "Control",
  llm: "LLM",
  tool: "Tool",
  browser: "Browser",
  readiness: "Readiness",
  verification: "Verification",
  evidence: "Evidence",
  recovery: "Recovery",
  approval: "Approval",
  error: "Error",
  review: "Review",
  report: "Report",
  budget: "Budget",
  planner: "Planner",
  verifier: "Verifier",
  task: "Task",
};

function graphNodeKey(node: RuntimeGraphNode) {
  const raw = node.metadata.raw;
  const rawAction =
    typeof raw === "object" && raw !== null && !Array.isArray(raw)
      ? String(
          (raw as Record<string, unknown>).action_type ??
            (raw as Record<string, unknown>).kind ??
            "",
        )
      : "";
  return [
    String(node.metadata.kind ?? ""),
    rawAction,
    node.label,
    node.id,
    node.type,
  ]
    .join(" ")
    .toLowerCase();
}

function graphNodeTitle(key: string, node: RuntimeGraphNode, language: Language) {
  const zh = language === "zh";
  if (key.includes("route_skill") || key.includes("skill_selected")) {
    return zh ? "技能路由" : "Skill routing";
  }
  if (key.includes("build_prompt") || key.includes("prompt")) {
    return zh ? "构建提示词" : "Prompt assembly";
  }
  if (key.includes("planner") || key.includes("plan")) {
    return zh ? "任务规划" : "Task planning";
  }
  if (key.includes("tool_call") || node.type === "tool") {
    return zh ? "工具调用" : "Tool call";
  }
  if (key.includes("tool_search") || key.includes("lazy_tool")) {
    return zh ? "工具搜索" : "Tool search";
  }
  if (key.includes("browser_open") || key.includes("navigation")) {
    return zh ? "页面打开" : "Page open";
  }
  if (key.includes("browser_observe") || key.includes("observe")) {
    return zh ? "页面观察" : "Page observation";
  }
  if (key.includes("browser") || key.includes("action_")) {
    return zh ? "浏览器动作" : "Browser action";
  }
  if (key.includes("readiness")) {
    return zh ? "页面就绪检查" : "Readiness check";
  }
  if (key.includes("verification") || key.includes("verifier")) {
    return zh ? "效果验证" : "Effect verification";
  }
  if (key.includes("report") || node.type === "report") {
    return zh ? "报告生成" : "Report generation";
  }
  if (key.includes("evidence") || node.type === "evidence") {
    return zh ? "证据采集" : "Evidence capture";
  }
  if (key.includes("review") || node.type === "review") return zh ? "结果审查" : "Result review";
  if (node.type === "llm") return zh ? "LLM 推理" : "LLM reasoning";
  if (node.type === "budget") return zh ? "预算检查" : "Budget check";
  if (node.type === "approval") return zh ? "人工审批" : "Human approval";
  if (node.type === "recovery") return zh ? "恢复处理" : "Recovery";
  if (node.type === "error") return zh ? "错误处理" : "Error handling";
  if (node.type === "task") return zh ? "任务状态" : "Task state";
  return zh ? categoryLabel(node.type, language) : node.label || categoryLabel(node.type, language);
}

function graphNodeResponsibility(
  key: string,
  node: RuntimeGraphNode,
  language: Language,
) {
  const zh = language === "zh";
  if (key.includes("route_skill") || key.includes("skill_selected")) {
    return zh
      ? "根据任务目标选择最合适的技能，并把任务交给对应工作流。"
      : "Selects the best skill for the task goal and routes the workflow.";
  }
  if (key.includes("build_prompt") || key.includes("prompt")) {
    return zh
      ? "组装当前任务上下文、工具约束、输出语言和报告要求。"
      : "Assembles task context, tool constraints, output language, and report requirements.";
  }
  if (key.includes("planner") || key.includes("plan")) {
    return zh
      ? "决定下一步动作，并把可执行意图交给浏览器或工具层。"
      : "Chooses the next action and passes executable intent to browser or tool layers.";
  }
  if (key.includes("tool_call") || node.type === "tool") {
    return zh
      ? "执行浏览器、研究或运行时工具，并记录结果与审计信息。"
      : "Runs browser, research, or runtime tools and records results plus audit data.";
  }
  if (key.includes("tool_search") || key.includes("lazy_tool")) {
    return zh
      ? "查找当前任务可用的 lazy tool，并决定是否加载到工具上下文。"
      : "Finds available lazy tools for the task and decides whether to load them into context.";
  }
  if (key.includes("browser_open") || key.includes("navigation")) {
    return zh
      ? "访问目标页面，建立初始页面状态并收集可观察信息。"
      : "Opens the target page, establishes page state, and captures initial observations.";
  }
  if (key.includes("browser_observe") || key.includes("observe")) {
    return zh
      ? "提取当前页面的可见信息、交互线索、风险信号和可引用证据。"
      : "Extracts visible page information, interaction cues, risk signals, and citable evidence.";
  }
  if (key.includes("browser") || key.includes("action_")) {
    return zh
      ? "在页面上执行读取或交互动作，并保存前后状态。"
      : "Executes read or interaction actions on the page and saves before/after state.";
  }
  if (key.includes("readiness")) {
    return zh
      ? "判断页面是否已达到可读取或可操作状态。"
      : "Checks whether the page is ready enough to read or operate on.";
  }
  if (key.includes("verification") || key.includes("verifier")) {
    return zh
      ? "验证动作效果是否符合预期，并标记失败或降级情况。"
      : "Verifies whether the action effect matched expectations and marks failures or degraded state.";
  }
  if (key.includes("report") || node.type === "report") {
    return zh
      ? "根据已采集证据产出最终分析报告，并保留证据引用。"
      : "Produces the final analytical report from captured evidence and keeps evidence references.";
  }
  if (key.includes("evidence") || node.type === "evidence") {
    return zh
      ? "保存截图、文本或页面片段，作为报告结论的支撑材料。"
      : "Saves screenshots, text, or page snippets as support for report conclusions.";
  }
  if (key.includes("review") || node.type === "review") {
    return zh
      ? "检查报告结论是否被证据支撑，并指出遗漏、风险或需要修订的内容。"
      : "Checks whether report conclusions are evidence-backed and flags omissions, risks, or revision needs.";
  }
  if (node.type === "llm") {
    return zh
      ? "生成或审查推理内容；调用详情保留在折叠详情中。"
      : "Generates or reviews reasoning content; call details stay in collapsed details.";
  }
  if (node.type === "budget") {
    return zh ? "检查本次运行是否符合预算策略。" : "Checks whether the run fits the budget policy.";
  }
  if (node.type === "approval") {
    return zh ? "暂停高风险操作并等待人工决策。" : "Pauses risky actions and waits for a human decision.";
  }
  if (node.type === "recovery") {
    return zh ? "尝试从错误、超时或页面异常中恢复。" : "Attempts to recover from errors, timeouts, or page issues.";
  }
  if (node.type === "error") {
    return zh ? "记录失败原因，帮助定位任务中断点。" : "Records failure context to locate where the task stopped.";
  }
  return zh ? "记录该运行节点的状态、摘要和相关调试信息。" : "Records this runtime node's state, summary, and related debug context.";
}

const ZH_EVENT: Record<string, { title: string; description: string }> = {
  workflow_node_started: { title: "工作流节点开始", description: "工作流进入新的执行节点。" },
  workflow_node_finished: { title: "工作流节点完成", description: "当前工作流节点已完成。" },
  browser_open_started: { title: "浏览器打开开始", description: "系统开始打开目标页面。" },
  browser_open_finished: { title: "浏览器打开完成", description: "页面已打开并完成初步观察。" },
  navigation_started: { title: "页面导航开始", description: "浏览器开始导航到目标页面。" },
  navigation_timeout: { title: "页面导航超时", description: "浏览器未在限定时间内等到页面完成加载，系统会尝试使用可用内容。" },
  navigation_degraded_ready: { title: "页面已部分可用", description: "页面未完全稳定，但已有可读取内容。" },
  tool_call_started: { title: "工具调用开始", description: "系统开始执行一个工具调用。" },
  tool_call_finished: { title: "工具调用完成", description: "工具调用已结束，结果保存在事件详情中。" },
  tool_audit: { title: "工具审计", description: "系统记录了工具调用审计信息。" },
  skill_selected: { title: "已选择技能", description: "系统已为任务选择技能。" },
  skill_loaded: { title: "技能已加载", description: "技能说明和上下文已加载。" },
  lazy_tool_search_started: { title: "Lazy Tool 搜索开始", description: "系统开始搜索可按需加载的工具。" },
  lazy_tool_loaded: { title: "Lazy Tool 已加载", description: "按需工具已加载到执行上下文。" },
  task_failed: { title: "任务失败", description: "任务已失败；错误详情保留在详情和 Debug 中。" },
  task_succeeded: { title: "任务成功", description: "任务已完成并生成可用结果。" },
  task_finished: { title: "任务完成", description: "工作流执行结束。" },
  report_generated: { title: "报告已生成", description: "系统已根据证据生成报告。" },
  report_written: { title: "报告已写入", description: "报告文件已保存到运行目录。" },
  evidence_added: { title: "证据已采集", description: "系统已保存新的页面证据。" },
  text_evidence_added: { title: "文本证据已采集", description: "系统已保存页面文本证据。" },
  screenshot_evidence_added: { title: "截图证据已采集", description: "系统已保存页面截图证据。" },
};

const EN_EVENT: Record<string, { title: string; description: string }> = {
  workflow_node_started: { title: "Workflow node started", description: "The workflow entered a new node." },
  workflow_node_finished: { title: "Workflow node finished", description: "The workflow node completed." },
  browser_open_started: { title: "Browser open started", description: "The browser started opening the target page." },
  browser_open_finished: { title: "Browser open finished", description: "The page was opened and initial observation completed." },
  navigation_started: { title: "Navigation started", description: "The browser started navigating to the target page." },
  navigation_timeout: { title: "Navigation timed out", description: "The page did not finish loading in time; available content may still be used." },
  navigation_degraded_ready: { title: "Page partially ready", description: "The page is not fully stable, but readable content is available." },
  tool_call_started: { title: "Tool call started", description: "A tool call started." },
  tool_call_finished: { title: "Tool call finished", description: "A tool call finished." },
  tool_audit: { title: "Tool audit", description: "Tool-call audit data was recorded." },
  skill_selected: { title: "Skill selected", description: "A task skill was selected." },
  skill_loaded: { title: "Skill loaded", description: "Skill instructions and context were loaded." },
  lazy_tool_search_started: { title: "Lazy tool search started", description: "The runtime started searching for on-demand tools." },
  lazy_tool_loaded: { title: "Lazy tool loaded", description: "An on-demand tool was loaded into context." },
  task_failed: { title: "Task failed", description: "The task failed." },
  task_succeeded: { title: "Task succeeded", description: "The task completed successfully." },
  task_finished: { title: "Task finished", description: "The workflow finished." },
  report_generated: { title: "Report generated", description: "A report was generated from evidence." },
  report_written: { title: "Report written", description: "The report file was saved to the run directory." },
  evidence_added: { title: "Evidence collected", description: "New page evidence was saved." },
  text_evidence_added: { title: "Text evidence collected", description: "Page text evidence was saved." },
  screenshot_evidence_added: { title: "Screenshot evidence collected", description: "Page screenshot evidence was saved." },
};
