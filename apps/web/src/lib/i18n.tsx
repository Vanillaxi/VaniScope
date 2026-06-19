"use client";

import { createContext, useContext, useEffect, useMemo, useState } from "react";

export type Language = "zh" | "en";

const STORAGE_KEY = "vaniscope.console.language";

const messages = {
  zh: {
    nav: {
      overview: "总览",
      newTask: "新建任务",
      evals: "评测结果",
      tagline: "LangGraph 浏览器 Agent Runtime",
      language: "界面语言",
      zh: "中文",
      en: "EN",
    },
    home: {
      title: "基于 LangGraph 的浏览器 Agent Runtime",
      description:
        "在一个控制台里创建本地浏览器任务、查看运行事件、检查 artifacts，并处理需要人工确认的审批关卡。",
      apiOk: "正常",
      apiDown: "不可用",
      apiChecking: "检查中",
      newTaskTitle: "新建任务",
      newTaskDescription:
        "填写 planner、点击意图、期望文本和可选 workspace，上交给 FastAPI 创建 LangGraph 浏览器任务。",
      open: "打开",
      taskByIdTitle: "按 ID 查看任务",
      taskId: "任务 ID",
      viewTask: "查看任务",
      evalTitle: "评测结果",
      evalDescription:
        "打开本地 LangGraph eval 命令辅助页，按输出目录查看生成的评测文件。",
    },
    taskCreate: {
      title: "新建任务",
      description: "通过 FastAPI Task API 提交 LangGraph 浏览器任务。",
      demoHint: "Demo 默认使用仓库内 mock site 路径，不访问真实网页。",
      url: "URL 或 fixture 路径",
      click: "点击目标 / 意图",
      expect: "期望文本",
      taskType: "任务类型",
      browserTask: "浏览器任务 browser_task",
      docsResearch: "文档研究 docs_research",
      skill: "Skill",
      autoSkill: "自动选择",
      query: "查询问题",
      researchGoal: "研究目标",
      language: "任务语言",
      autoLanguage: "自动 auto",
      planner: "Planner",
      deterministic: "确定性 deterministic",
      fakeLlm: "模拟 LLM fake_llm",
      llm: "真实 LLM llm",
      workspace: "Workspace 路径",
      riskMode: "风险模式",
      readOnly: "只读 read_only",
      approvalRequired: "需要审批 approval_required",
      reminder: "运行提醒",
      reminderPlaceholder: "可选的 runtime reminder",
      fillDemo: "填入 demo case",
      docsDemo: "Docs Research Demo",
      docsDemoZh: "中文 Docs Demo",
      creating: "创建中...",
      create: "创建任务",
      demoReminder: "This is a local full-stack console demo.",
      docsDemoReminder: "This is a local docs research demo.",
    },
    taskDetail: {
      unavailable: "任务不可用",
      loading: "正在加载任务...",
      artifacts: "任务产物",
      refreshArtifacts: "刷新产物",
      finalReportPreview: "Final report 预览",
    },
    status: {
      task: "任务",
      currentPhase: "当前阶段",
      updatedAt: "更新时间",
      currentStep: "当前步骤",
      runDir: "运行目录",
      createdAt: "创建时间",
      artifactCount: "产物数量",
      taskType: "任务类型",
      skillId: "Skill",
      skillStatus: "Skill 状态",
      unknown: "未知",
      waiting: "等待中",
      missing: "缺失",
      running: "运行中",
      succeeded: "已成功",
      failed: "已失败",
      requires_approval: "等待审批",
      resuming: "恢复中",
      blocked: "已阻止",
      rejected: "已拒绝",
      not_found: "未找到",
    },
    events: {
      title: "事件流",
      manualRefresh: "手动刷新",
      empty: "暂无事件。",
      live: "实时连接",
      polling: "轮询回退",
      unavailable: "暂不可用",
      connecting: "连接中",
      invalidSse: "收到无法解析的 SSE 事件，已跳过。",
      invalidJsonl: "events.jsonl 中存在无法解析的事件行，已跳过。",
    },
    artifacts: {
      empty: "暂无 artifacts。",
      viewer: "任务产物查看器",
      select: "请选择 artifact",
      loading: "正在加载 artifact...",
      noneSelected: "尚未选择 artifact。",
      refresh: "刷新",
      skillResult: "Skill 结果",
      truncated: "已截断，原始内容共 {count} 个字符。",
    },
    approvals: {
      title: "审批",
      description: "高风险工具调用会暂停任务，等待人工确认后再继续。",
      refresh: "刷新",
      empty: "暂无审批请求。",
      tool: "工具",
      riskLevel: "风险等级",
      requestedAction: "请求动作",
      createdAt: "创建时间",
      approve: "批准",
      reject: "拒绝",
      approved: "已批准",
      rejected: "已拒绝",
      pending: "待审批",
      approvedReason: "在控制台批准",
      rejectedReason: "在控制台拒绝",
      unknown: "未知",
    },
    evals: {
      title: "评测结果",
      description:
        "当前 MVP 保持 eval 输出为本地文件模式。运行 LangGraph eval 后，从选定输出目录查看生成的 artifacts。",
      outputPath: "Eval 输出路径",
      command: "命令",
    },
  },
  en: {
    nav: {
      overview: "Overview",
      newTask: "New Task",
      evals: "Eval Results",
      tagline: "LangGraph Browser Agent Runtime",
      language: "Language",
      zh: "中文",
      en: "EN",
    },
    home: {
      title: "LangGraph-based Browser Agent Runtime",
      description:
        "Create local browser tasks, watch runtime events, inspect artifacts, and resolve human approval gates from one console.",
      apiOk: "OK",
      apiDown: "Unavailable",
      apiChecking: "Checking",
      newTaskTitle: "New Task",
      newTaskDescription:
        "Submit planner, click intent, expected text, and optional workspace context to create a LangGraph browser task through FastAPI.",
      open: "Open",
      taskByIdTitle: "View Task by ID",
      taskId: "Task ID",
      viewTask: "View Task",
      evalTitle: "Eval Results",
      evalDescription:
        "Open the local LangGraph eval command helper and inspect generated result files by output directory.",
    },
    taskCreate: {
      title: "Create Task",
      description: "Submit a LangGraph browser task through the FastAPI Task API.",
      demoHint: "The demo uses repository mock-site fixtures and does not access real websites.",
      url: "URL or fixture path",
      click: "Click target / intent",
      expect: "Expected text",
      taskType: "Task type",
      browserTask: "browser_task",
      docsResearch: "docs_research",
      skill: "Skill",
      autoSkill: "Auto",
      query: "Query",
      researchGoal: "Research goal",
      language: "Task language",
      autoLanguage: "auto",
      planner: "Planner",
      deterministic: "deterministic",
      fakeLlm: "fake_llm",
      llm: "llm",
      workspace: "Workspace path",
      riskMode: "Risk mode",
      readOnly: "read_only",
      approvalRequired: "approval_required",
      reminder: "Reminder",
      reminderPlaceholder: "Optional runtime reminder",
      fillDemo: "Fill demo case",
      docsDemo: "Docs Research Demo",
      docsDemoZh: "Chinese Docs Demo",
      creating: "Creating...",
      create: "Create Task",
      demoReminder: "This is a local full-stack console demo.",
      docsDemoReminder: "This is a local docs research demo.",
    },
    taskDetail: {
      unavailable: "Task unavailable",
      loading: "Loading task...",
      artifacts: "Artifacts",
      refreshArtifacts: "Refresh artifacts",
      finalReportPreview: "Final report preview",
    },
    status: {
      task: "Task",
      currentPhase: "Current phase",
      updatedAt: "Updated",
      currentStep: "Current step",
      runDir: "Run directory",
      createdAt: "Created",
      artifactCount: "Artifact count",
      taskType: "Task type",
      skillId: "Skill",
      skillStatus: "Skill status",
      unknown: "Unknown",
      waiting: "Waiting",
      missing: "Missing",
      running: "Running",
      succeeded: "Succeeded",
      failed: "Failed",
      requires_approval: "Requires approval",
      resuming: "Resuming",
      blocked: "Blocked",
      rejected: "Rejected",
      not_found: "Not found",
    },
    events: {
      title: "Events",
      manualRefresh: "Refresh",
      empty: "No events yet.",
      live: "Live",
      polling: "Polling fallback",
      unavailable: "Disconnected",
      connecting: "Connecting",
      invalidSse: "Received an invalid SSE event; skipped it.",
      invalidJsonl: "events.jsonl contains an invalid event line; skipped it.",
    },
    artifacts: {
      empty: "No artifacts yet.",
      viewer: "Artifact viewer",
      select: "Select an artifact",
      loading: "Loading artifact...",
      noneSelected: "No artifact selected.",
      refresh: "Refresh",
      skillResult: "Skill result",
      truncated: "Truncated. Original content has {count} characters.",
    },
    approvals: {
      title: "Approvals",
      description: "Risky tool calls pause the task until a human decision is submitted.",
      refresh: "Refresh",
      empty: "No approval requests.",
      tool: "Tool",
      riskLevel: "Risk level",
      requestedAction: "Requested action",
      createdAt: "Created",
      approve: "Approve",
      reject: "Reject",
      approved: "Approved",
      rejected: "Rejected",
      pending: "Pending",
      approvedReason: "Approved from console",
      rejectedReason: "Rejected from console",
      unknown: "Unknown",
    },
    evals: {
      title: "Eval Results",
      description:
        "This MVP keeps eval output file-based. Run the LangGraph eval locally and inspect generated artifacts from the selected output directory.",
      outputPath: "Eval output path",
      command: "Command",
    },
  },
};

type Messages = (typeof messages)["zh"];

type I18nContextValue = {
  language: Language;
  setLanguage: (language: Language) => void;
  t: Messages;
};

const I18nContext = createContext<I18nContextValue | null>(null);

export function LanguageProvider({ children }: { children: React.ReactNode }) {
  const [language, setLanguageState] = useState<Language>("zh");

  useEffect(() => {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    const timer = window.setTimeout(() => {
      if (stored === "zh" || stored === "en") {
        setLanguageState(stored);
      }
    }, 0);
    return () => window.clearTimeout(timer);
  }, []);

  const setLanguage = (nextLanguage: Language) => {
    setLanguageState(nextLanguage);
    window.localStorage.setItem(STORAGE_KEY, nextLanguage);
  };

  const value = useMemo(
    () => ({
      language,
      setLanguage,
      t: messages[language],
    }),
    [language],
  );

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n() {
  const value = useContext(I18nContext);
  if (value === null) {
    throw new Error("useI18n must be used within LanguageProvider");
  }
  return value;
}
