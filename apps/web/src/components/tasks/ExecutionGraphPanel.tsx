"use client";

import { useMemo, useState } from "react";
import { Badge } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";
import { formatDateTime } from "@/lib/format";
import { useI18n } from "@/lib/i18n";
import { graphNodeDisplay, statusLabel } from "@/lib/localizedDisplay";
import type { RuntimeExecutionGraphResponse, RuntimeGraphNode } from "@/lib/types";

type ExecutionGraphPanelProps = {
  graph?: RuntimeExecutionGraphResponse | null;
  onInspectNode?: (node: NonNullable<RuntimeExecutionGraphResponse["nodes"]>[number]) => void;
};

export function ExecutionGraphPanel({
  graph,
  onInspectNode,
}: ExecutionGraphPanelProps) {
  const { language, t } = useI18n();
  const nodes = useMemo(() => graph?.nodes ?? [], [graph?.nodes]);
  const groups = useMemo(() => groupGraphNodes(nodes, language), [nodes, language]);
  const [selectedId, setSelectedId] = useState<string | null>(groups[0]?.id ?? null);
  const [expandedRaw, setExpandedRaw] = useState<Record<string, boolean>>({});
  const effectiveSelectedId =
    groups.some((group) => group.id === selectedId) ? selectedId : groups[0]?.id;
  const selectedGroup = useMemo(
    () => groups.find((group) => group.id === effectiveSelectedId) ?? groups[0],
    [groups, effectiveSelectedId],
  );

  return (
    <div className="grid gap-5">
      <Card className="p-5">
        <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 className="text-lg font-semibold">{t.inspector.executionGraph}</h2>
            <p className="mt-1 text-sm text-[var(--muted)]">
              {groups.length} {t.inspector.graphNodes} · {nodes.length}{" "}
              {t.inspector.groupedNodes} · {graph?.edges.length ?? 0} {t.inspector.graphEdges}
              {graph?.fallback ? ` · ${t.inspector.fallbackGraph}` : ""}
            </p>
          </div>
          {graph?.error ? <Badge tone="danger">{graph.error}</Badge> : null}
        </div>

        {groups.length ? (
          <div className="rounded-md border border-[var(--line)] bg-[#fbfcfd] p-4">
            <div className="grid gap-3">
              {groups.map((group, index) => {
                const rawOpen = expandedRaw[group.id] === true;
                return (
                  <article
                    key={group.id}
                    className={`rounded-md border bg-white p-4 shadow-sm transition ${
                      selectedGroup?.id === group.id
                        ? "border-[var(--brand)] ring-2 ring-[#cde8ea]"
                        : "border-[var(--line)]"
                    }`}
                  >
                    <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
                      <button
                        type="button"
                        onClick={() => {
                          setSelectedId(group.id);
                          onInspectNode?.(group.primary);
                        }}
                        className="min-w-0 flex-1 text-left"
                      >
                        <div className="flex flex-wrap items-center gap-2">
                          <span
                            className={`h-2.5 w-2.5 rounded-full ${statusDotClass(group.status)}`}
                          />
                          <span className="text-xs font-semibold text-[var(--muted)]">
                            {String(index + 1).padStart(2, "0")}
                          </span>
                          <Badge tone={typeTone(group.type)}>{group.display.type}</Badge>
                          <Badge tone={statusTone(group.status)}>
                            {statusLabel(group.status, language)}
                          </Badge>
                          <span className="text-xs text-[var(--muted)]">
                            {formatDateTime(group.timestamp, language, "")}
                          </span>
                          {group.durationMs !== null ? (
                            <span className="text-xs font-semibold text-[#344054]">
                              {formatDuration(group.durationMs)}
                            </span>
                          ) : null}
                        </div>
                        <h3 className="mt-2 truncate font-semibold text-[#26323f]">
                          {group.display.label}
                        </h3>
                      </button>
                      <button
                        type="button"
                        onClick={() =>
                          setExpandedRaw((current) => ({
                            ...current,
                            [group.id]: !rawOpen,
                          }))
                        }
                        className="inline-flex min-h-8 shrink-0 items-center rounded-md border border-[var(--line)] px-3 text-xs font-semibold text-[var(--brand-dark)] hover:bg-[var(--panel-soft)]"
                      >
                        {rawOpen ? t.inspector.hideDetails : t.inspector.showDetails}
                      </button>
                    </div>

                    <div className="mt-3 grid gap-3 text-sm lg:grid-cols-2">
                      <div className="rounded-md bg-[var(--panel-soft)] p-3">
                        <div className="text-xs font-semibold uppercase text-[var(--muted)]">
                          {t.inspector.nodeResponsibility}
                        </div>
                        <div className="mt-1 leading-6 text-[#344054]">
                          {group.display.responsibility}
                        </div>
                      </div>
                      <div className="rounded-md bg-[var(--panel-soft)] p-3">
                        <div className="text-xs font-semibold uppercase text-[var(--muted)]">
                          {t.inspector.nodeSummary}
                        </div>
                        <div className="mt-1 leading-6 text-[#344054]">
                          {group.summary}
                        </div>
                      </div>
                    </div>

                    {group.steps.length ? (
                      <div className="mt-3 rounded-md border border-[var(--line)] bg-white p-3 text-sm">
                        <div className="text-xs font-semibold uppercase text-[var(--muted)]">
                          {t.inspector.traceChain}
                        </div>
                        <ol className="mt-2 grid gap-1.5">
                          {group.steps.map((step, stepIndex) => (
                            <li
                              key={`${step.id}-${stepIndex}`}
                              className="flex min-w-0 items-start gap-2 text-[#344054]"
                            >
                              <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-[#9fb1bf]" />
                              <span className="min-w-0">
                                <span className="font-medium">{step.title}</span>
                                {step.summary ? (
                                  <span className="text-[var(--muted)]"> - {step.summary}</span>
                                ) : null}
                              </span>
                            </li>
                          ))}
                        </ol>
                      </div>
                    ) : null}

                    {rawOpen ? (
                      <div className="mt-3">
                        <div className="mb-2 text-xs font-semibold uppercase text-[var(--muted)]">
                          {t.inspector.rawDetails}
                        </div>
                        <pre className="max-h-96 overflow-auto rounded-md bg-[#101828] p-3 text-xs leading-5 text-[#f8fafc]">
                          {JSON.stringify(
                            {
                              group_id: group.id,
                              responsibility: group.display.responsibility,
                              nodes: group.nodes.map((node) => ({
                                id: node.id,
                                label: node.label,
                                status: node.status,
                                timestamp: node.timestamp,
                                duration_ms: node.duration_ms,
                                metadata: node.metadata,
                              })),
                            },
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
          </div>
        ) : (
          <div className="rounded-md border border-dashed border-[var(--line)] p-5 text-sm text-[var(--muted)]">
            {t.inspector.noGraphNodes}
          </div>
        )}
      </Card>
    </div>
  );
}

type PresentedGraphGroup = {
  id: string;
  primary: RuntimeGraphNode;
  nodes: RuntimeGraphNode[];
  display: ReturnType<typeof graphNodeDisplay>;
  type: string;
  status: string;
  timestamp?: string | null;
  durationMs: number | null;
  summary: string;
  steps: { id: string; title: string; summary: string }[];
};

function groupGraphNodes(
  nodes: RuntimeGraphNode[],
  language: "zh" | "en",
): PresentedGraphGroup[] {
  const groups: PresentedGraphGroup[] = [];
  for (const node of nodes) {
    const display = graphNodeDisplay(node, language);
    const last = groups.at(-1);
    if (last && last.display.responsibility === display.responsibility) {
      last.nodes.push(node);
      last.status = mergeStatus(last.status, node.status);
      last.durationMs = mergeDuration(last.durationMs, node.duration_ms);
      last.summary = groupSummary(last.nodes);
      last.steps = groupSteps(last.nodes, language);
      continue;
    }
    groups.push({
      id: `group:${groups.length}:${node.id}`,
      primary: node,
      nodes: [node],
      display,
      type: node.type,
      status: node.status,
      timestamp: node.timestamp,
      durationMs: node.duration_ms ?? null,
      summary: groupSummary([node]),
      steps: groupSteps([node], language),
    });
  }
  return groups;
}

function groupSummary(nodes: RuntimeGraphNode[]) {
  const summaries = uniqueCompact(
    nodes.map((node) => node.summary || node.label || node.id),
  );
  return summaries.slice(0, 2).join(" / ");
}

function groupSteps(nodes: RuntimeGraphNode[], language: "zh" | "en") {
  return nodes.map((node) => {
    const display = graphNodeDisplay(node, language);
    return {
      id: node.id,
      title: node.label || display.label || node.id,
      summary: node.summary && node.summary !== node.label ? node.summary : "",
    };
  });
}

function uniqueCompact(values: string[]) {
  const seen = new Set<string>();
  const result: string[] = [];
  for (const value of values) {
    const normalized = value.trim().replace(/\s+/g, " ");
    if (!normalized || seen.has(normalized)) continue;
    seen.add(normalized);
    result.push(normalized);
  }
  return result;
}

function mergeDuration(current: number | null, next?: number | null) {
  if (next === null || next === undefined) return current;
  return (current ?? 0) + next;
}

function mergeStatus(current: string, next: string) {
  const values = [current.toLowerCase(), next.toLowerCase()];
  if (values.some((value) => ["failed", "error", "blocked", "rejected", "timeout"].includes(value))) {
    return next;
  }
  if (values.some((value) => ["pending", "running", "approval_required", "requires_approval"].includes(value))) {
    return next;
  }
  return next || current;
}

function formatDuration(value: number) {
  if (value >= 1000) return `${(value / 1000).toFixed(1)}s`;
  return `${Math.round(value)}ms`;
}

function typeTone(type: string) {
  if (type === "llm" || type === "planner") return "info";
  if (type === "approval" || type === "recovery") return "warning";
  if (type === "evidence" || type === "report") return "success";
  if (type === "error") return "danger";
  return "neutral";
}

function statusTone(status: string) {
  const value = status.toLowerCase();
  if (["success", "succeeded", "passed", "generated", "collected"].includes(value)) {
    return "success";
  }
  if (["failed", "error", "blocked", "rejected", "timeout"].includes(value)) {
    return "danger";
  }
  if (["pending", "running", "approval_required", "requires_approval"].includes(value)) {
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
  if (["pending", "approval_required", "requires_approval"].includes(value)) {
    return "bg-[#dc6803]";
  }
  return "bg-[#1570ef]";
}
