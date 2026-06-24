"use client";

import { useMemo, useState } from "react";
import { Badge } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";
import { formatDateTime } from "@/lib/format";
import { useI18n, type Language } from "@/lib/i18n";
import { statusLabel } from "@/lib/localizedDisplay";
import type { RuntimeExecutionGraphResponse, RuntimeGraphNode } from "@/lib/types";

type ExecutionGraphPanelProps = {
  graph?: RuntimeExecutionGraphResponse | null;
  onInspectNode?: (node: NonNullable<RuntimeExecutionGraphResponse["nodes"]>[number]) => void;
};

type PhaseType =
  | "task_start"
  | "skill_route"
  | "prompt_build"
  | "planning"
  | "plan_validation"
  | "execution"
  | "browser_open"
  | "browser_observe"
  | "evidence_collect"
  | "report_generate"
  | "review"
  | "task_finish";

type PhaseDefinition = {
  type: PhaseType;
  zhTitle: string;
  enTitle: string;
  zhResponsibility: string;
  enResponsibility: string;
};

type ExecutionSubstep = {
  title: string;
  status: string;
  timestamp?: string | null;
  shortDetail: string;
  rawEventId: string;
};

type ExecutionGraphPhase = {
  id: string;
  order: number;
  phaseType: PhaseType;
  title: string;
  responsibility: string;
  status: string;
  startedAt?: string | null;
  finishedAt?: string | null;
  durationMs: number | null;
  inputSummary: string;
  outputSummary: string;
  keyResult: string;
  modelInfo?: string;
  toolInfo?: string;
  evidenceIds: string[];
  artifactIds: string[];
  warnings: string[];
  substeps: ExecutionSubstep[];
  rawEvents: RuntimeGraphNode[];
};

const PHASES: PhaseDefinition[] = [
  {
    type: "task_start",
    zhTitle: "任务初始化",
    enTitle: "Task initialization",
    zhResponsibility: "创建任务运行上下文，记录目标、URL、运行目录和初始状态。",
    enResponsibility: "Create the run context and record the goal, URL, run directory, and initial state.",
  },
  {
    type: "skill_route",
    zhTitle: "技能路由",
    enTitle: "Skill routing",
    zhResponsibility: "根据用户目标、URL 和页面类型选择合适的技能或使用通用浏览器任务。",
    enResponsibility: "Choose the best skill from the goal, URL, and page type, or use the generic browser task.",
  },
  {
    type: "prompt_build",
    zhTitle: "构建提示词",
    enTitle: "Prompt build",
    zhResponsibility: "组装任务目标、当前上下文、可用工具、技能规则和输出约束。",
    enResponsibility: "Assemble the goal, current context, available tools, skill rules, and output constraints.",
  },
  {
    type: "planning",
    zhTitle: "LLM 任务规划",
    enTitle: "LLM planning",
    zhResponsibility: "调用规划器或 LLM，根据目标和上下文决定下一步动作。",
    enResponsibility: "Call the planner or LLM to decide the next action from the goal and context.",
  },
  {
    type: "plan_validation",
    zhTitle: "计划校验",
    enTitle: "Plan validation",
    zhResponsibility: "校验模型输出的动作是否合法、安全，并符合 Browser Tool Contract v2。",
    enResponsibility: "Validate that proposed actions are legal, safe, and compatible with Browser Tool Contract v2.",
  },
  {
    type: "execution",
    zhTitle: "执行计划",
    enTitle: "Plan execution",
    zhResponsibility: "将规划结果交给 ToolGateway 和 Browser Runtime 执行。",
    enResponsibility: "Hand planned actions to ToolGateway and the Browser Runtime for execution.",
  },
  {
    type: "browser_open",
    zhTitle: "页面打开",
    enTitle: "Page open",
    zhResponsibility: "访问目标页面，建立浏览器会话和初始页面状态。",
    enResponsibility: "Open the target page and establish the browser session plus initial page state.",
  },
  {
    type: "browser_observe",
    zhTitle: "页面观察",
    enTitle: "Page observation",
    zhResponsibility: "读取页面可见内容、交互元素和页面状态，形成可供规划/报告使用的 observation。",
    enResponsibility: "Read visible content, interaction elements, and page state as an observation for planning/reporting.",
  },
  {
    type: "evidence_collect",
    zhTitle: "证据采集",
    enTitle: "Evidence collection",
    zhResponsibility: "记录截图、文本证据、页面观察和关键运行产物。",
    enResponsibility: "Record screenshots, text evidence, page observations, and key runtime artifacts.",
  },
  {
    type: "report_generate",
    zhTitle: "报告生成",
    enTitle: "Report generation",
    zhResponsibility: "基于证据链和任务目标生成最终分析报告。",
    enResponsibility: "Generate the final analysis report from the evidence chain and task goal.",
  },
  {
    type: "review",
    zhTitle: "结果审查",
    enTitle: "Result review",
    zhResponsibility: "检查报告结论是否有证据支撑，标记 unsupported claims。",
    enResponsibility: "Check whether report conclusions are evidence-backed and flag unsupported claims.",
  },
  {
    type: "task_finish",
    zhTitle: "任务完成",
    enTitle: "Task finish",
    zhResponsibility: "保存最终状态、报告、证据和运行结果。",
    enResponsibility: "Persist the final status, report, evidence, and run result.",
  },
];

export function ExecutionGraphPanel({
  graph,
  onInspectNode,
}: ExecutionGraphPanelProps) {
  const { language, t } = useI18n();
  const rawNodes = useMemo(() => graph?.nodes ?? [], [graph?.nodes]);
  const phases = useMemo(
    () => buildExecutionPhases(rawNodes, language, t),
    [language, rawNodes, t],
  );
  const [expandedRaw, setExpandedRaw] = useState<Record<string, boolean>>({});

  return (
    <Card className="p-5">
      <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold">{t.inspector.executionGraph}</h2>
          <p className="mt-1 text-sm text-[var(--muted)]">
            {phases.length} {t.inspector.executionPhases} · {rawNodes.length}{" "}
            {t.inspector.rawEvents}
            {graph?.fallback ? ` · ${t.inspector.fallbackGraph}` : ""}
          </p>
        </div>
        {graph?.error ? <Badge tone="danger">{graph.error}</Badge> : null}
      </div>

      {rawNodes.length ? (
        <div className="relative grid gap-3 rounded-md border border-[var(--line)] bg-[#fbfcfd] p-3">
          {phases.map((phase) => {
            const rawOpen = expandedRaw[phase.id] === true;
            const disabled = phase.status === "skipped";
            return (
              <article
                key={phase.id}
                className={`relative rounded-md border bg-white p-3 transition ${
                  disabled
                    ? "border-dashed border-[var(--line)] opacity-75"
                    : "border-[var(--line)] shadow-sm"
                }`}
              >
                <div className="flex flex-col gap-2 md:flex-row md:items-start md:justify-between">
                  <button
                    type="button"
                    onClick={() => phase.rawEvents[0] && onInspectNode?.(phase.rawEvents[0])}
                    className="min-w-0 flex-1 text-left"
                    disabled={!phase.rawEvents.length}
                  >
                    <div className="flex flex-wrap items-center gap-2">
                      <span className={`h-2.5 w-2.5 rounded-full ${statusDotClass(phase.status)}`} />
                      <span className="text-xs font-semibold text-[var(--muted)]">
                        {String(phase.order).padStart(2, "0")}
                      </span>
                      <Badge tone={statusTone(phase.status)}>
                        {statusLabel(phase.status, language)}
                      </Badge>
                      {phase.startedAt ? (
                        <span className="text-xs text-[var(--muted)]">
                          {formatDateTime(phase.startedAt, language, "")}
                        </span>
                      ) : null}
                      {phase.durationMs !== null ? (
                        <span className="text-xs font-semibold text-[#344054]">
                          {formatDuration(phase.durationMs)}
                        </span>
                      ) : null}
                    </div>
                    <h3 className="mt-1 text-base font-semibold text-[#26323f]">
                      {phase.title}
                    </h3>
                  </button>
                  <button
                    type="button"
                    onClick={() =>
                      setExpandedRaw((current) => ({
                        ...current,
                        [phase.id]: !rawOpen,
                      }))
                    }
                    className="inline-flex min-h-8 shrink-0 items-center rounded-md border border-[var(--line)] px-3 text-xs font-semibold text-[var(--brand-dark)] hover:bg-[var(--panel-soft)] disabled:cursor-not-allowed disabled:opacity-50"
                    disabled={!phase.rawEvents.length}
                  >
                    {rawOpen ? t.inspector.hideDetails : t.inspector.showDetails}
                  </button>
                </div>

                <div className="mt-3 grid gap-2 text-sm md:grid-cols-2 xl:grid-cols-4">
                  <PhaseMeta label={t.inspector.nodeResponsibility} value={phase.responsibility} />
                  <PhaseMeta label={t.inspector.inputSummary} value={phase.inputSummary} />
                  <PhaseMeta label={t.inspector.outputSummary} value={phase.outputSummary} />
                  <PhaseMeta label={t.inspector.keyResult} value={phase.keyResult} />
                </div>

                <div className="mt-3 flex flex-wrap gap-2 text-xs">
                  {phase.modelInfo ? <Badge tone="info">{phase.modelInfo}</Badge> : null}
                  {phase.toolInfo ? <Badge tone="neutral">{phase.toolInfo}</Badge> : null}
                  {phase.evidenceIds.length ? (
                    <Badge tone="success">
                      {t.inspector.evidence}: {phase.evidenceIds.length}
                    </Badge>
                  ) : null}
                  {phase.artifactIds.length ? (
                    <Badge tone="neutral">
                      {t.inspector.artifacts}: {phase.artifactIds.join(", ")}
                    </Badge>
                  ) : null}
                  {phase.warnings.map((warning) => (
                    <Badge key={warning} tone="warning">
                      {warning}
                    </Badge>
                  ))}
                </div>

                {phase.substeps.length ? (
                  <div className="mt-3 rounded-md border border-[var(--line)] bg-[#fbfcfd] p-3 text-sm">
                    <div className="text-xs font-semibold uppercase text-[var(--muted)]">
                      {t.inspector.traceChain}
                    </div>
                    <ol className="mt-2 grid gap-1.5">
                      {phase.substeps.slice(0, 6).map((step, index) => (
                        <li
                          key={`${step.rawEventId}-${index}`}
                          className="flex min-w-0 items-start gap-2 text-[#344054]"
                        >
                          <span className={`mt-2 h-1.5 w-1.5 shrink-0 rounded-full ${statusDotClass(step.status)}`} />
                          <span className="min-w-0">
                            <span className="font-medium">{step.title}</span>
                            {step.shortDetail ? (
                              <span className="text-[var(--muted)]"> - {step.shortDetail}</span>
                            ) : null}
                          </span>
                        </li>
                      ))}
                      {phase.substeps.length > 6 ? (
                        <li className="text-xs font-semibold text-[var(--muted)]">
                          +{phase.substeps.length - 6} {t.inspector.rawEvents}
                        </li>
                      ) : null}
                    </ol>
                  </div>
                ) : null}

                {rawOpen ? (
                  <div className="mt-3">
                    <div className="mb-2 text-xs font-semibold uppercase text-[var(--muted)]">
                      {t.inspector.rawEvents}
                    </div>
                    <pre className="max-h-96 overflow-auto rounded-md bg-[#101828] p-3 text-xs leading-5 text-[#f8fafc]">
                      {JSON.stringify(
                        phase.rawEvents.map((node) => ({
                          id: node.id,
                          type: node.type,
                          label: node.label,
                          status: node.status,
                          timestamp: node.timestamp,
                          duration_ms: node.duration_ms,
                          metadata: node.metadata,
                        })),
                        null,
                        2,
                      )}
                    </pre>
                  </div>
                ) : null}
              </article>
            );
          })}
        </div>
      ) : (
        <div className="rounded-md border border-dashed border-[var(--line)] p-5 text-sm text-[var(--muted)]">
          {t.inspector.noGraphNodes}
        </div>
      )}
    </Card>
  );
}

function PhaseMeta({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md bg-[var(--panel-soft)] p-3">
      <div className="text-xs font-semibold uppercase text-[var(--muted)]">
        {label}
      </div>
      <div className="mt-1 leading-6 text-[#344054]">{value}</div>
    </div>
  );
}

function buildExecutionPhases(
  nodes: RuntimeGraphNode[],
  language: Language,
  t: ReturnType<typeof useI18n>["t"],
): ExecutionGraphPhase[] {
  const buckets = new Map<PhaseType, RuntimeGraphNode[]>(
    PHASES.map((phase) => [phase.type, []]),
  );
  for (const node of nodes) {
    buckets.get(classifyPhase(node))?.push(node);
  }

  return PHASES.map((definition, index) =>
    buildPhase(definition, index + 1, buckets.get(definition.type) ?? [], language, t),
  );
}

function buildPhase(
  definition: PhaseDefinition,
  order: number,
  rawEvents: RuntimeGraphNode[],
  language: Language,
  t: ReturnType<typeof useI18n>["t"],
): ExecutionGraphPhase {
  const startedAt = firstTimestamp(rawEvents);
  const finishedAt = lastTimestamp(rawEvents);
  const status = rawEvents.length ? mergeStatuses(rawEvents.map((node) => node.status)) : "skipped";
  const evidenceIds = unique(rawEvents.flatMap(evidenceIdsFromNode));
  const artifactIds = unique(rawEvents.flatMap(artifactIdsFromNode));
  const warnings = unique(rawEvents.flatMap(warningsFromNode));
  const modelInfo = modelInfoFromNodes(rawEvents);
  const toolInfo = toolInfoFromNodes(rawEvents);
  return {
    id: `phase:${definition.type}`,
    order,
    phaseType: definition.type,
    title: language === "zh" ? definition.zhTitle : definition.enTitle,
    responsibility:
      language === "zh" ? definition.zhResponsibility : definition.enResponsibility,
    status,
    startedAt,
    finishedAt,
    durationMs: durationForNodes(rawEvents, startedAt, finishedAt),
    inputSummary: phaseInputSummary(definition.type, rawEvents, language, t),
    outputSummary: phaseOutputSummary(definition.type, rawEvents, language, t),
    keyResult: phaseKeyResult(definition.type, rawEvents, language, t),
    modelInfo,
    toolInfo,
    evidenceIds,
    artifactIds,
    warnings,
    substeps: rawEvents.map((node) => ({
      title: substepTitle(node, language),
      status: node.status,
      timestamp: node.timestamp,
      shortDetail: node.summary || "",
      rawEventId: node.id,
    })),
    rawEvents,
  };
}

function classifyPhase(node: RuntimeGraphNode): PhaseType {
  const key = nodeKey(node);
  const raw = rawRecord(node);
  const toolName = String(raw?.tool_name ?? raw?.tool_id ?? raw?.name ?? "").toLowerCase();
  const workflowNode = String(
    valueFrom(raw, "node") ??
      valueFrom(raw, "node_name") ??
      valueFrom(raw, "workflow_node") ??
      valueFrom(raw, "current_node") ??
      "",
  ).toLowerCase();
  const combined = `${key} ${toolName} ${workflowNode}`;

  if (includesAny(combined, ["task_failed", "task_succeeded", "task_finished", "workflow finished", "finish_task"])) {
    return "task_finish";
  }
  if (includesAny(combined, ["review", "unsupported_claim", "report_review"])) return "review";
  if (includesAny(combined, ["report", "final_report", "build_report", "partial_report"])) {
    return "report_generate";
  }
  if (includesAny(combined, ["evidence", "screenshot", "artifact_created"])) {
    return "evidence_collect";
  }
  if (includesAny(combined, ["browser_observe", "observe", "observation", "readiness"])) {
    return "browser_observe";
  }
  if (includesAny(combined, ["browser_open", "navigation", "page open"])) return "browser_open";
  if (includesAny(combined, ["execute_plan", "tool_call", "tool_audit", "toolgateway"])) {
    return "execution";
  }
  if (includesAny(combined, ["validate_plan", "validation", "schema", "rejected action", "llm_action_rejected"])) {
    return "plan_validation";
  }
  if (node.type === "llm" || includesAny(combined, ["plan_task", "planner", "llm_call", "llm_action", "planning"])) {
    return "planning";
  }
  if (includesAny(combined, ["build_prompt", "prompt_preview", "prompt_tool", "lazy_tool", "tool catalog"])) {
    return "prompt_build";
  }
  if (includesAny(combined, ["route_skill", "skill_registry", "skill_selection", "skill_selected", "skill_loaded", "skill_not_selected"])) {
    return "skill_route";
  }
  if (includesAny(combined, ["task_created", "task_started", "created"])) return "task_start";
  if (node.type === "tool") return "execution";
  if (node.type === "task") return "task_start";
  return "execution";
}

function phaseInputSummary(
  phaseType: PhaseType,
  nodes: RuntimeGraphNode[],
  language: Language,
  t: ReturnType<typeof useI18n>["t"],
) {
  if (!nodes.length) return t.inspector.phaseSkipped;
  const source = firstValue(nodes, ["target_url", "url", "source_url"]);
  const goal = firstValue(nodes, ["goal", "query", "raw_task", "summary_instruction"]);
  const tool = firstValue(nodes, ["tool_name", "tool_id"]);
  const evidenceCount = unique(nodes.flatMap(evidenceIdsFromNode)).length;
  if (phaseType === "browser_open" && source) return source;
  if (phaseType === "execution" && tool) return `${t.inspector.tools}: ${tool}`;
  if (phaseType === "report_generate") {
    return language === "zh" ? `证据数：${evidenceCount}` : `Evidence count: ${evidenceCount}`;
  }
  return goal || source || tool || compact(nodes[0]?.summary || nodes[0]?.label || nodes[0]?.id);
}

function phaseOutputSummary(
  phaseType: PhaseType,
  nodes: RuntimeGraphNode[],
  language: Language,
  t: ReturnType<typeof useI18n>["t"],
) {
  if (!nodes.length) return t.inspector.phaseNotRun;
  const urlAfter = firstValue(nodes, ["url_after", "url", "source_url"]);
  const title = firstValue(nodes, ["title_after", "title", "page_title"]);
  const evidenceIds = unique(nodes.flatMap(evidenceIdsFromNode));
  const artifacts = unique(nodes.flatMap(artifactIdsFromNode));
  if (phaseType === "browser_open" && urlAfter) return urlAfter;
  if (phaseType === "browser_observe" && title) return title;
  if (phaseType === "evidence_collect") {
    return language === "zh" ? `采集 ${evidenceIds.length} 条证据` : `Collected ${evidenceIds.length} evidence item(s)`;
  }
  if (phaseType === "report_generate" && artifacts.length) return artifacts.join(", ");
  return compact(lastNonEmpty(nodes.map((node) => node.summary || node.label || node.id)) || "");
}

function phaseKeyResult(
  phaseType: PhaseType,
  nodes: RuntimeGraphNode[],
  language: Language,
  t: ReturnType<typeof useI18n>["t"],
) {
  if (!nodes.length) return t.inspector.phaseSkipped;
  const status = statusLabel(mergeStatuses(nodes.map((node) => node.status)), language);
  const model = modelInfoFromNodes(nodes);
  const tool = toolInfoFromNodes(nodes);
  if (phaseType === "planning" && model) return model;
  if (phaseType === "execution" && tool) return tool;
  if (phaseType === "report_generate") {
    const artifacts = unique(nodes.flatMap(artifactIdsFromNode));
    return artifacts.includes("final_report.md")
      ? "final_report.md"
      : language === "zh"
        ? "报告已生成"
        : "Report generated";
  }
  return status;
}

function nodeKey(node: RuntimeGraphNode) {
  const raw = rawRecord(node);
  return [
    node.id,
    node.type,
    node.label,
    node.status,
    node.summary,
    node.metadata.kind,
    node.metadata.source,
    valueFrom(raw, "kind"),
    valueFrom(raw, "event"),
    valueFrom(raw, "action_type"),
    valueFrom(raw, "message"),
    valueFrom(raw, "purpose"),
    valueFrom(raw, "node"),
    valueFrom(raw, "node_name"),
    valueFrom(raw, "tool_name"),
  ]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
}

function rawRecord(node: RuntimeGraphNode): Record<string, unknown> | null {
  const raw = node.metadata.raw;
  if (isRecord(raw)) return raw;
  const payload = node.metadata.payload;
  if (isRecord(payload)) return payload;
  return isRecord(node.metadata) ? node.metadata : null;
}

function substepTitle(node: RuntimeGraphNode, language: Language) {
  const raw = rawRecord(node);
  const kind =
    String(raw?.kind ?? raw?.event ?? node.metadata.kind ?? node.label ?? node.id)
      .replaceAll("_", " ")
      .trim();
  const source = typeof node.metadata.source === "string" ? node.metadata.source : "";
  if (language === "zh" && source) return `${kind} (${source})`;
  return source ? `${kind} (${source})` : kind;
}

function firstValue(nodes: RuntimeGraphNode[], keys: string[]) {
  for (const node of nodes) {
    const raw = rawRecord(node);
    for (const key of keys) {
      const value = valueFrom(node.metadata, key) ?? valueFrom(raw, key);
      if (typeof value === "string" && value) return compact(value, 180);
    }
  }
  return "";
}

function valueFrom(record: Record<string, unknown> | null | undefined, key: string): unknown {
  if (!record) return undefined;
  if (record[key] !== undefined) return record[key];
  const payload = record.payload;
  if (isRecord(payload) && payload[key] !== undefined) return payload[key];
  const observation = record.observation;
  if (isRecord(observation) && observation[key] !== undefined) return observation[key];
  return undefined;
}

function modelInfoFromNodes(nodes: RuntimeGraphNode[]) {
  for (const node of nodes) {
    const raw = rawRecord(node);
    const provider = valueFrom(raw, "provider");
    const model = valueFrom(raw, "model");
    if (provider || model) {
      return [provider, model].filter(Boolean).join(" / ");
    }
    if (node.type === "llm" && node.summary) return node.summary;
  }
  return undefined;
}

function toolInfoFromNodes(nodes: RuntimeGraphNode[]) {
  const tools = unique(
    nodes
      .map((node) => String(valueFrom(rawRecord(node), "tool_name") ?? valueFrom(rawRecord(node), "tool_id") ?? ""))
      .filter(Boolean),
  );
  return tools.length ? tools.slice(0, 3).join(", ") : undefined;
}

function evidenceIdsFromNode(node: RuntimeGraphNode) {
  const raw = rawRecord(node);
  const ids = [
    valueFrom(raw, "evidence_id"),
    valueFrom(raw, "screenshot_evidence_id"),
    ...(Array.isArray(valueFrom(raw, "evidence_ids")) ? (valueFrom(raw, "evidence_ids") as unknown[]) : []),
    ...(Array.isArray(node.metadata.evidence_ids) ? node.metadata.evidence_ids : []),
  ];
  return ids.filter((value): value is string => typeof value === "string" && value.length > 0);
}

function artifactIdsFromNode(node: RuntimeGraphNode) {
  const raw = rawRecord(node);
  const source = typeof node.metadata.source === "string" ? node.metadata.source : "";
  const path = valueFrom(raw, "report_path") ?? valueFrom(raw, "final_report_path") ?? valueFrom(raw, "artifact_name");
  return unique(
    [source, typeof path === "string" ? path.split(/[\\/]/).pop() : ""]
      .filter((value): value is string => Boolean(value)),
  ).filter((value) => value !== "events.jsonl" && value !== "trace.jsonl");
}

function warningsFromNode(node: RuntimeGraphNode) {
  const raw = rawRecord(node);
  return [
    valueFrom(raw, "warning"),
    valueFrom(raw, "error"),
    valueFrom(raw, "error_message"),
    node.status === "failed" || node.status === "blocked" ? node.summary : "",
  ].filter((value): value is string => typeof value === "string" && value.length > 0);
}

function firstTimestamp(nodes: RuntimeGraphNode[]) {
  return nodes.find((node) => node.timestamp)?.timestamp ?? null;
}

function lastTimestamp(nodes: RuntimeGraphNode[]) {
  return [...nodes].reverse().find((node) => node.timestamp)?.timestamp ?? null;
}

function durationForNodes(
  nodes: RuntimeGraphNode[],
  startedAt?: string | null,
  finishedAt?: string | null,
) {
  const explicit = nodes
    .map((node) => node.duration_ms)
    .filter((value): value is number => typeof value === "number")
    .reduce((sum, value) => sum + value, 0);
  if (explicit > 0) return explicit;
  if (startedAt && finishedAt) {
    const delta = new Date(finishedAt).getTime() - new Date(startedAt).getTime();
    return Number.isFinite(delta) && delta > 0 ? delta : null;
  }
  return null;
}

function mergeStatuses(statuses: string[]) {
  const values = statuses.map((status) => status.toLowerCase());
  if (values.some((value) => ["failed", "error", "rejected", "timeout"].includes(value))) return "failed";
  if (values.some((value) => ["blocked", "approval_required", "requires_approval"].includes(value))) return "blocked";
  if (values.some((value) => ["warning", "degraded"].includes(value))) return "warning";
  if (values.some((value) => ["running", "pending"].includes(value))) return "running";
  if (values.length === 0) return "skipped";
  return "success";
}

function includesAny(value: string, candidates: string[]) {
  return candidates.some((candidate) => value.includes(candidate));
}

function unique(values: string[]) {
  return Array.from(new Set(values.filter(Boolean)));
}

function lastNonEmpty(values: string[]) {
  return [...values].reverse().find((value) => value.trim());
}

function compact(value: string, limit = 220) {
  const normalized = value.replace(/\s+/g, " ").trim();
  if (normalized.length <= limit) return normalized;
  return `${normalized.slice(0, limit - 3)}...`;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function formatDuration(value: number) {
  if (value >= 1000) return `${(value / 1000).toFixed(1)}s`;
  return `${Math.round(value)}ms`;
}

function statusTone(status: string) {
  const value = status.toLowerCase();
  if (["success", "succeeded", "passed", "generated", "collected"].includes(value)) {
    return "success";
  }
  if (["failed", "error", "blocked", "rejected", "timeout"].includes(value)) {
    return "danger";
  }
  if (["pending", "running", "approval_required", "requires_approval", "warning"].includes(value)) {
    return "warning";
  }
  return "neutral";
}

function statusDotClass(status: string) {
  const value = status.toLowerCase();
  if (["success", "succeeded", "passed", "generated", "collected"].includes(value)) {
    return "bg-[var(--success)]";
  }
  if (["failed", "error", "blocked", "rejected", "timeout"].includes(value)) {
    return "bg-[var(--danger)]";
  }
  if (["pending", "running", "approval_required", "requires_approval", "warning"].includes(value)) {
    return "bg-[#dc6803]";
  }
  return "bg-[#98a2b3]";
}
