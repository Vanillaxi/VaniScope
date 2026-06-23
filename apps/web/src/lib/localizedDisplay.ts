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
  const label =
    language === "zh"
      ? `${type}${tool ? `：${tool}` : ""}`
      : `${type}${tool ? `: ${tool}` : ""}`;
  return { label, status, type };
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
};

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
