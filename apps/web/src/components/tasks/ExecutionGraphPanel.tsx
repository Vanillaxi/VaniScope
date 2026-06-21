"use client";

import { useMemo, useState } from "react";
import { Badge } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";
import { StepDetailPanel } from "@/components/tasks/StepDetailPanel";
import { formatDateTime } from "@/lib/format";
import { useI18n } from "@/lib/i18n";
import type {
  RuntimeEvidenceLink,
  RuntimeExecutionGraphResponse,
  RuntimeGraphNode,
} from "@/lib/types";

type ExecutionGraphPanelProps = {
  taskId: string;
  graph?: RuntimeExecutionGraphResponse | null;
  evidence?: RuntimeEvidenceLink[];
};

const ROW_HEIGHT = 126;
const NODE_WIDTH = 520;

export function ExecutionGraphPanel({
  taskId,
  graph,
  evidence = [],
}: ExecutionGraphPanelProps) {
  const { language } = useI18n();
  const nodes = graph?.nodes ?? [];
  const [selectedId, setSelectedId] = useState<string | null>(nodes[0]?.id ?? null);
  const selectedNode = useMemo(
    () => nodes.find((node) => node.id === (selectedId ?? nodes[0]?.id)) ?? nodes[0],
    [nodes, selectedId],
  );

  return (
    <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_430px]">
      <Card className="p-5">
        <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 className="text-lg font-semibold">Execution Graph</h2>
            <p className="mt-1 text-sm text-[var(--muted)]">
              {nodes.length} nodes · {graph?.edges.length ?? 0} edges
              {graph?.fallback ? " · fallback" : ""}
            </p>
          </div>
          {graph?.error ? <Badge tone="danger">{graph.error}</Badge> : null}
        </div>

        {nodes.length ? (
          <div className="overflow-x-auto rounded-md border border-[var(--line)] bg-[#fbfcfd] p-4">
            <div
              className="relative mx-auto"
              style={{
                width: NODE_WIDTH,
                height: Math.max(ROW_HEIGHT, nodes.length * ROW_HEIGHT),
              }}
            >
              <svg
                className="pointer-events-none absolute inset-0"
                width={NODE_WIDTH}
                height={Math.max(ROW_HEIGHT, nodes.length * ROW_HEIGHT)}
                aria-hidden="true"
              >
                {nodes.slice(0, -1).map((node, index) => (
                  <line
                    key={`line-${node.id}`}
                    x1={NODE_WIDTH / 2}
                    y1={index * ROW_HEIGHT + 92}
                    x2={NODE_WIDTH / 2}
                    y2={(index + 1) * ROW_HEIGHT + 18}
                    stroke="#b8c2cc"
                    strokeWidth="2"
                  />
                ))}
              </svg>
              {nodes.map((node, index) => (
                <button
                  key={node.id}
                  type="button"
                  onClick={() => setSelectedId(node.id)}
                  className={`absolute left-0 w-full rounded-md border bg-white p-3 text-left shadow-sm transition ${
                    selectedNode?.id === node.id
                      ? "border-[var(--brand)] ring-2 ring-[#cde8ea]"
                      : "border-[var(--line)] hover:border-[#9fb1bf]"
                  }`}
                  style={{ top: index * ROW_HEIGHT, minHeight: 100 }}
                >
                  <div className="flex flex-wrap items-center gap-2">
                    <span
                      className={`h-2.5 w-2.5 rounded-full ${statusDotClass(node.status)}`}
                    />
                    <Badge tone={typeTone(node.type)}>{node.type}</Badge>
                    <Badge tone={statusTone(node.status)}>{node.status}</Badge>
                    <span className="text-xs text-[var(--muted)]">
                      {formatDateTime(node.timestamp, language, "")}
                    </span>
                    {node.duration_ms !== null && node.duration_ms !== undefined ? (
                      <span className="text-xs font-semibold text-[#344054]">
                        {formatDuration(node.duration_ms)}
                      </span>
                    ) : null}
                  </div>
                  <div className="mt-2 overflow-hidden text-ellipsis whitespace-nowrap font-semibold text-[#26323f]">
                    {node.label}
                  </div>
                  {node.summary ? (
                    <div className="mt-1 max-h-10 overflow-hidden text-sm leading-5 text-[var(--muted)]">
                      {node.summary}
                    </div>
                  ) : null}
                </button>
              ))}
            </div>
          </div>
        ) : (
          <div className="rounded-md border border-dashed border-[var(--line)] p-5 text-sm text-[var(--muted)]">
            No graph nodes yet.
          </div>
        )}
      </Card>

      <StepDetailPanel
        taskId={taskId}
        title="Node Detail"
        node={selectedNode}
        evidence={evidence}
      />
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
