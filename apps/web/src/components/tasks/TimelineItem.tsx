"use client";

import { useState } from "react";
import { Badge } from "@/components/ui/Badge";
import { formatDateTime } from "@/lib/format";
import { useI18n } from "@/lib/i18n";
import { eventDisplay } from "@/lib/localizedDisplay";
import type { RuntimeTimelineItem } from "@/lib/types";

type TimelineItemProps = {
  item: RuntimeTimelineItem;
  selected?: boolean;
  onSelect?: (item: RuntimeTimelineItem) => void;
};

export function TimelineItem({ item, selected = false, onSelect }: TimelineItemProps) {
  const { language, t } = useI18n();
  const [expanded, setExpanded] = useState(false);
  const display = eventDisplay(item, language);

  return (
    <div
      className={`border-b border-[var(--line)] bg-white p-4 last:border-b-0 ${
        selected ? "shadow-[inset_3px_0_0_var(--brand)]" : ""
      }`}
    >
      <button
        type="button"
        onClick={() => {
          onSelect?.(item);
          setExpanded((value) => !value);
        }}
        className="flex w-full flex-col gap-3 text-left"
      >
        <div className="flex flex-wrap items-center gap-2">
          <Badge tone={categoryTone(item.category)}>{display.category}</Badge>
          {item.status ? <Badge tone={statusTone(item.status)}>{display.status}</Badge> : null}
          <span className="text-xs text-[var(--muted)]">
            {formatDateTime(item.timestamp, language, "")}
          </span>
          {item.duration_ms !== null && item.duration_ms !== undefined ? (
            <span className="text-xs font-semibold text-[#344054]">
              {formatDuration(item.duration_ms)}
            </span>
          ) : null}
        </div>
        <div>
          <div className="font-semibold text-[#26323f]">{display.title}</div>
          {display.description ? (
            <div className="mt-1 text-sm leading-6 text-[var(--muted)]">
              {display.description}
            </div>
          ) : null}
        </div>
      </button>
      {expanded ? (
        <div className="mt-4 grid gap-3">
          <div className="grid gap-2 text-sm sm:grid-cols-3">
            <Meta label={t.inspector.category} value={display.category} />
            <Meta label={t.inspector.status} value={display.status} />
            <Meta label="Step" value={item.step_id} />
            <Meta label="Tool" value={item.tool_name} />
            <Meta label={t.inspector.evidenceLinked} value={item.evidence_ids.join(", ")} />
            <Meta
              label={t.inspector.artifactRefs}
              value={item.artifact_refs.map((ref) => ref.artifact_name).join(", ")}
            />
          </div>
          <div>
            <div className="mb-2 text-xs font-semibold uppercase text-[var(--muted)]">
              {t.inspector.rawPayload}
            </div>
            <pre className="max-h-80 overflow-auto rounded-md bg-[#101828] p-3 text-xs leading-5 text-[#f8fafc]">
              {JSON.stringify(item.raw ?? {}, null, 2)}
            </pre>
          </div>
        </div>
      ) : null}
    </div>
  );
}

function formatDuration(value: number) {
  if (value >= 1000) return `${(value / 1000).toFixed(1)}s`;
  return `${Math.round(value)}ms`;
}

function Meta({ label, value }: { label: string; value?: string | null }) {
  return (
    <div>
      <div className="text-xs font-semibold uppercase text-[var(--muted)]">{label}</div>
      <div className="mt-1 break-words text-[#344054]">{value || "-"}</div>
    </div>
  );
}

function categoryTone(category: string) {
  if (category === "llm") return "info";
  if (category === "approval" || category === "recovery") return "warning";
  if (category === "review" || category === "report") return "success";
  if (category === "tool") return "neutral";
  return "info";
}

function statusTone(status: string) {
  const value = status.toLowerCase();
  if (["success", "succeeded", "passed", "generated", "collected"].includes(value)) {
    return "success";
  }
  if (["failed", "error", "blocked", "rejected", "skipped"].includes(value)) {
    return "danger";
  }
  if (["pending", "running", "requires_approval"].includes(value)) return "warning";
  return "neutral";
}
