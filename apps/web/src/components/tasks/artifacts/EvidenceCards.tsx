"use client";

import { Badge } from "@/components/ui/Badge";

type EvidenceCardsProps = {
  rows: Record<string, unknown>[];
};

export function EvidenceCards({ rows }: EvidenceCardsProps) {
  if (!rows.length) {
    return (
      <div className="rounded-md border border-dashed border-[var(--line)] p-5 text-sm text-[var(--muted)]">
        No evidence records.
      </div>
    );
  }
  return (
    <div className="grid gap-3">
      {rows.map((row, index) => {
        const evidenceId = stringValue(row.evidence_id) || `evidence_${index + 1}`;
        return (
          <div key={`${evidenceId}-${index}`} className="rounded-md border border-[var(--line)] bg-white p-4">
            <div className="flex flex-wrap items-center gap-2">
              <Badge tone="info">{evidenceId}</Badge>
              {stringValue(row.kind) ? <Badge>{stringValue(row.kind)}</Badge> : null}
              {stringValue(row.skill_id) ? <Badge>{stringValue(row.skill_id)}</Badge> : null}
            </div>
            {stringValue(row.page_title) ? (
              <h3 className="mt-3 text-base font-semibold text-[#1d2939]">
                {stringValue(row.page_title)}
              </h3>
            ) : null}
            {stringValue(row.source_url) ? (
              <div className="mt-2 break-all text-xs text-[var(--muted)]">
                {stringValue(row.source_url)}
              </div>
            ) : null}
            {stringValue(row.text) ? (
              <div className="mt-3 rounded-md bg-[var(--panel-soft)] p-3 text-sm leading-6 text-[#344054]">
                {stringValue(row.text)}
              </div>
            ) : null}
            <div className="mt-3 grid gap-3 text-xs text-[var(--muted)] sm:grid-cols-2">
              <Meta label="Section" value={stringValue(row.section)} />
              <Meta label="Trace" value={stringValue(row.trace_event_id)} />
            </div>
          </div>
        );
      })}
    </div>
  );
}

function Meta({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="font-semibold uppercase">{label}</div>
      <div className="mt-1 break-words text-[#344054]">{value || "-"}</div>
    </div>
  );
}

function stringValue(value: unknown) {
  return typeof value === "string" ? value : "";
}
