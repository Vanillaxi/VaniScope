"use client";

import { useMemo, useState } from "react";
import { StepDetailPanel } from "@/components/tasks/StepDetailPanel";
import { TimelineItem } from "@/components/tasks/TimelineItem";
import { Badge } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";
import { useI18n } from "@/lib/i18n";
import type {
  RuntimeEvidenceLink,
  RuntimeInspectorSummary,
  RuntimeTimelineItem,
} from "@/lib/types";

type TimelinePanelProps = {
  taskId: string;
  items: RuntimeTimelineItem[];
  summary?: RuntimeInspectorSummary | null;
  evidence?: RuntimeEvidenceLink[];
};

const FILTERS = [
  "workflow",
  "llm",
  "tool",
  "browser",
  "readiness",
  "verification",
  "evidence",
  "recovery",
  "approval",
  "error",
];

const KEY_EVENTS = new Set([
  "task_started",
  "planner_started",
  "llm_call_finished",
  "llm_action_proposed",
  "tool_call_started",
  "tool_call_finished",
  "readiness_wait_finished",
  "readiness_timeout",
  "effect_verification_finished",
  "recovery_started",
  "recovery_finished",
  "evidence_added",
  "screenshot_evidence_added",
  "text_evidence_added",
  "task_succeeded",
  "task_finished",
  "task_failed",
]);

export function TimelinePanel({
  taskId,
  items,
  summary,
  evidence = [],
}: TimelinePanelProps) {
  const { t } = useI18n();
  const [showLowLevel, setShowLowLevel] = useState(false);
  const [activeFilters, setActiveFilters] = useState<Set<string>>(new Set(FILTERS));
  const [selectedId, setSelectedId] = useState<string | null>(items[0]?.id ?? null);
  const filteredItems = useMemo(
    () =>
      items.filter((item) => {
        const visibleByLevel =
          showLowLevel || KEY_EVENTS.has(item.kind) || !item.kind.startsWith("workflow_node_");
        return visibleByLevel && activeFilters.has(item.category);
      }),
    [activeFilters, items, showLowLevel],
  );
  const selectedItem =
    filteredItems.find((item) => item.id === selectedId) ?? filteredItems[0] ?? null;

  return (
    <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_430px]">
      <Card className="p-5">
        <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 className="text-lg font-semibold">{t.inspector.timeline}</h2>
            <p className="mt-1 text-sm text-[var(--muted)]">
              {summary
                ? `${filteredItems.length}/${summary.timeline_count} items · ${summary.evidence_count} evidence · ${summary.llm_call_count} LLM`
                : t.inspector.summary}
            </p>
          </div>
          <label className="flex items-center gap-2 text-sm font-semibold text-[#344054]">
            <input
              type="checkbox"
              checked={showLowLevel}
              onChange={(event) => setShowLowLevel(event.target.checked)}
            />
            Show low-level workflow events
          </label>
        </div>
        <div className="mb-4 flex flex-wrap gap-2">
          {FILTERS.map((filter) => (
            <button
              key={filter}
              type="button"
              onClick={() => setActiveFilters((current) => toggleFilter(current, filter))}
              className="rounded"
            >
              <Badge tone={activeFilters.has(filter) ? "info" : "neutral"}>{filter}</Badge>
            </button>
          ))}
        </div>
        <div className="overflow-hidden rounded-md border border-[var(--line)]">
          {filteredItems.length ? (
            filteredItems.map((item, index) => (
              <TimelineItem
                key={timelineItemKey(item, index)}
                item={item}
                selected={selectedItem?.id === item.id}
                onSelect={(nextItem) => setSelectedId(nextItem.id)}
              />
            ))
          ) : (
            <div className="p-4 text-sm text-[var(--muted)]">{t.inspector.noTimeline}</div>
          )}
        </div>
      </Card>
      <StepDetailPanel
        taskId={taskId}
        title="Event Detail"
        item={selectedItem}
        evidence={evidence}
      />
    </div>
  );
}

function toggleFilter(current: Set<string>, value: string) {
  const next = new Set(current);
  if (next.has(value)) next.delete(value);
  else next.add(value);
  return next;
}

function timelineItemKey(item: RuntimeTimelineItem, index: number) {
  const source =
    item.source ??
    item.raw_ref?.artifact_name ??
    item.artifact_refs[0]?.artifact_name ??
    "timeline";
  return `${source}-${item.kind ?? "item"}-${item.id ?? "no-id"}-${index}`;
}
