"use client";

import { TimelineItem } from "@/components/tasks/TimelineItem";
import { Card } from "@/components/ui/Card";
import { useI18n } from "@/lib/i18n";
import type { RuntimeInspectorSummary, RuntimeTimelineItem } from "@/lib/types";

type TimelinePanelProps = {
  items: RuntimeTimelineItem[];
  summary?: RuntimeInspectorSummary | null;
};

export function TimelinePanel({ items, summary }: TimelinePanelProps) {
  const { t } = useI18n();

  return (
    <Card className="p-5">
      <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold">{t.inspector.timeline}</h2>
          <p className="mt-1 text-sm text-[var(--muted)]">
            {summary
              ? `${summary.timeline_count} items · ${summary.evidence_count} evidence · ${summary.llm_call_count} LLM`
              : t.inspector.summary}
          </p>
        </div>
      </div>
      <div className="overflow-hidden rounded-md border border-[var(--line)]">
        {items.length ? (
          items.map((item) => <TimelineItem key={item.id} item={item} />)
        ) : (
          <div className="p-4 text-sm text-[var(--muted)]">{t.inspector.noTimeline}</div>
        )}
      </div>
    </Card>
  );
}
