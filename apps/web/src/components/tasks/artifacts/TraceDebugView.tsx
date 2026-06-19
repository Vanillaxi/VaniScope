"use client";

import { Badge } from "@/components/ui/Badge";
import { formatDateTime } from "@/lib/format";

type TraceDebugViewProps = {
  rows: Record<string, unknown>[];
  label: string;
};

export function TraceDebugView({ rows, label }: TraceDebugViewProps) {
  const categories = unique(
    rows.map((row) => stringValue(row.category) || stringValue(row.kind) || stringValue(row.action_type)),
  );
  const timestamps = rows
    .map((row) => stringValue(row.timestamp) || stringValue(row.created_at))
    .filter(Boolean);

  return (
    <div className="rounded-md border border-[var(--line)] bg-white p-5">
      <div className="flex flex-wrap gap-2">
        <Badge tone="info">{label}: {rows.length}</Badge>
        <Badge>First: {formatDateTime(timestamps[0], "en", "-")}</Badge>
        <Badge>Last: {formatDateTime(timestamps.at(-1), "en", "-")}</Badge>
      </div>
      {categories.length ? (
        <div className="mt-4 flex flex-wrap gap-2">
          {categories.slice(0, 16).map((category) => (
            <Badge key={category}>{category}</Badge>
          ))}
        </div>
      ) : null}
    </div>
  );
}

function unique(values: string[]) {
  return Array.from(new Set(values.filter(Boolean)));
}

function stringValue(value: unknown) {
  return typeof value === "string" ? value : "";
}
