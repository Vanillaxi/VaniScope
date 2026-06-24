"use client";

import { useMemo, useState } from "react";
import { Badge } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";
import { formatDateTime } from "@/lib/format";
import { useI18n } from "@/lib/i18n";
import { graphNodeDisplay } from "@/lib/localizedDisplay";
import type { RuntimeExecutionGraphResponse } from "@/lib/types";

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
  const [selectedId, setSelectedId] = useState<string | null>(nodes[0]?.id ?? null);
  const [expandedRaw, setExpandedRaw] = useState<Record<string, boolean>>({});
  const effectiveSelectedId =
    nodes.some((node) => node.id === selectedId) ? selectedId : nodes[0]?.id;
  const selectedNode = useMemo(
    () => nodes.find((node) => node.id === effectiveSelectedId) ?? nodes[0],
    [nodes, effectiveSelectedId],
  );

  return (
    <div className="grid gap-5">
      <Card className="p-5">
        <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 className="text-lg font-semibold">{t.inspector.executionGraph}</h2>
            <p className="mt-1 text-sm text-[var(--muted)]">
              {nodes.length} {t.inspector.graphNodes} · {graph?.edges.length ?? 0} {t.inspector.graphEdges}
              {graph?.fallback ? ` · ${t.inspector.fallbackGraph}` : ""}
            </p>
          </div>
          {graph?.error ? <Badge tone="danger">{graph.error}</Badge> : null}
        </div>

        {nodes.length ? (
          <div className="rounded-md border border-[var(--line)] bg-[#fbfcfd] p-4">
            <div className="grid gap-3">
              {nodes.map((node, index) => {
                const display = graphNodeDisplay(node, language);
                const rawOpen = expandedRaw[node.id] === true;
                return (
                  <article
                    key={node.id}
                    className={`rounded-md border bg-white p-4 shadow-sm transition ${
                      selectedNode?.id === node.id
                        ? "border-[var(--brand)] ring-2 ring-[#cde8ea]"
                        : "border-[var(--line)]"
                    }`}
                  >
                    <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
                      <button
                        type="button"
                        onClick={() => {
                          setSelectedId(node.id);
                          onInspectNode?.(node);
                        }}
                        className="min-w-0 flex-1 text-left"
                      >
                        <div className="flex flex-wrap items-center gap-2">
                          <span
                            className={`h-2.5 w-2.5 rounded-full ${statusDotClass(node.status)}`}
                          />
                          <span className="text-xs font-semibold text-[var(--muted)]">
                            {String(index + 1).padStart(2, "0")}
                          </span>
                          <Badge tone={typeTone(node.type)}>{display.type}</Badge>
                          <Badge tone={statusTone(node.status)}>{display.status}</Badge>
                          <span className="text-xs text-[var(--muted)]">
                            {formatDateTime(node.timestamp, language, "")}
                          </span>
                          {node.duration_ms !== null && node.duration_ms !== undefined ? (
                            <span className="text-xs font-semibold text-[#344054]">
                              {formatDuration(node.duration_ms)}
                            </span>
                          ) : null}
                        </div>
                        <h3 className="mt-2 truncate font-semibold text-[#26323f]">
                          {display.label}
                        </h3>
                      </button>
                      <button
                        type="button"
                        onClick={() =>
                          setExpandedRaw((current) => ({
                            ...current,
                            [node.id]: !rawOpen,
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
                          {display.responsibility}
                        </div>
                      </div>
                      <div className="rounded-md bg-[var(--panel-soft)] p-3">
                        <div className="text-xs font-semibold uppercase text-[var(--muted)]">
                          {t.inspector.nodeSummary}
                        </div>
                        <div className="mt-1 leading-6 text-[#344054]">
                          {node.summary || node.label || node.id}
                        </div>
                      </div>
                    </div>

                    {rawOpen ? (
                      <div className="mt-3">
                        <div className="mb-2 text-xs font-semibold uppercase text-[var(--muted)]">
                          {t.inspector.rawDetails}
                        </div>
                        <pre className="max-h-96 overflow-auto rounded-md bg-[#101828] p-3 text-xs leading-5 text-[#f8fafc]">
                          {JSON.stringify(
                            {
                              id: node.id,
                              label: node.label,
                              metadata: node.metadata,
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
