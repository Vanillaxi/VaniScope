"use client";

import { useMemo, useState } from "react";
import { Card } from "@/components/ui/Card";
import { screenshotUrl } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import type { RuntimeEvidenceLink } from "@/lib/types";

type EvidencePanelProps = {
  taskId: string;
  evidence: RuntimeEvidenceLink[];
  onInspectEvidence?: (item: RuntimeEvidenceLink) => void;
};

export function EvidencePanel({
  taskId,
  evidence,
  onInspectEvidence,
}: EvidencePanelProps) {
  const { t } = useI18n();
  const groups = useMemo(() => groupEvidence(evidence), [evidence]);
  const [expandedGroups, setExpandedGroups] = useState<Record<string, boolean>>({});

  return (
    <Card className="p-5">
      <div className="mb-4">
        <h2 className="text-lg font-semibold">{t.inspector.evidence}</h2>
        <p className="mt-1 text-sm text-[var(--muted)]">
          {groups.length} {t.inspector.distinctEvidence} · {evidence.length}{" "}
          {t.inspector.evidenceLinked}
        </p>
      </div>
      {groups.length ? (
        <div className="grid gap-3">
          {groups.map((group) => {
            const primary = group.items[0];
            const expanded = expandedGroups[group.id] === true;
            const similarCount = group.items.length - 1;
            return (
              <div
                key={group.id}
                className="rounded-md border border-[var(--line)] bg-white p-4 transition hover:border-[#9fb1bf]"
              >
                <EvidenceCard
                  taskId={taskId}
                  item={primary}
                  onInspectEvidence={onInspectEvidence}
                />
                {similarCount > 0 ? (
                  <div className="mt-3 border-t border-[var(--line)] pt-3">
                    <button
                      type="button"
                      onClick={() =>
                        setExpandedGroups((current) => ({
                          ...current,
                          [group.id]: !expanded,
                        }))
                      }
                      className="rounded px-2 py-1 text-xs font-semibold text-[var(--brand-dark)] hover:bg-[var(--panel-soft)]"
                    >
                      {expanded
                        ? t.inspector.hideSimilarEvidence
                        : `+${similarCount} ${t.inspector.similarEvidence}`}
                    </button>
                    {expanded ? (
                      <div className="mt-3 grid gap-3">
                        {group.items.slice(1).map((item) => (
                          <div
                            key={item.evidence_id}
                            className="rounded-md border border-dashed border-[var(--line)] bg-[var(--panel-soft)] p-3"
                          >
                            <EvidenceCard
                              taskId={taskId}
                              item={item}
                              onInspectEvidence={onInspectEvidence}
                              compact
                            />
                          </div>
                        ))}
                      </div>
                    ) : null}
                  </div>
                ) : null}
              </div>
            );
          })}
        </div>
      ) : (
        <div className="rounded-md border border-dashed border-[var(--line)] p-5 text-sm text-[var(--muted)]">
          {t.inspector.noEvidence}
        </div>
      )}
    </Card>
  );
}

function EvidenceCard({
  taskId,
  item,
  onInspectEvidence,
  compact = false,
}: {
  taskId: string;
  item: RuntimeEvidenceLink;
  onInspectEvidence?: (item: RuntimeEvidenceLink) => void;
  compact?: boolean;
}) {
  const { t } = useI18n();
  return (
    <>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <button
          type="button"
          onClick={() => onInspectEvidence?.(item)}
          className="min-w-0 text-left"
        >
          <span className="font-semibold text-[var(--brand-dark)]">
            {item.evidence_id}
          </span>
          {item.page_title ? (
            <span className="ml-2 text-sm text-[var(--muted)]">{item.page_title}</span>
          ) : null}
        </button>
        {onInspectEvidence ? (
          <button
            type="button"
            onClick={() => onInspectEvidence(item)}
            className="rounded px-2 py-1 text-xs font-semibold text-[var(--brand-dark)] hover:bg-white/70"
          >
            {t.inspector.details}
          </button>
        ) : null}
      </div>
      {item.source_url ? (
        <div className="mt-2 break-all text-xs text-[var(--muted)]">
          <span className="font-semibold">{t.inspector.sourceUrl}: </span>
          {item.source_url}
        </div>
      ) : null}
      {item.text_preview ? (
        <div className="mt-3 rounded-md bg-[var(--panel-soft)] p-3 text-sm leading-6 text-[#344054]">
          {item.text_preview}
        </div>
      ) : null}
      {!compact ? <ScreenshotPreview taskId={taskId} item={item} /> : null}
      <div className="mt-3 grid gap-3 text-sm sm:grid-cols-2">
        <Meta label={t.inspector.reportSections} values={item.report_sections} />
        <Meta label={t.inspector.reviewIssues} values={item.review_issue_ids} />
        <Meta
          label={t.inspector.relatedEvent}
          values={
            typeof item.raw.trace_event_id === "string"
              ? [item.raw.trace_event_id]
              : []
          }
        />
      </div>
    </>
  );
}

function ScreenshotPreview({
  taskId,
  item,
}: {
  taskId: string;
  item: RuntimeEvidenceLink;
}) {
  const path = typeof item.raw.screenshot_path === "string" ? item.raw.screenshot_path : null;
  const src = screenshotUrl(taskId, path);
  if (!src) return null;
  return (
    <a
      href={src}
      target="_blank"
      rel="noreferrer"
      className="mt-3 block overflow-hidden rounded-md border border-[var(--line)] bg-white"
    >
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src={src} alt={item.evidence_id} className="aspect-video w-full object-cover" />
    </a>
  );
}

function Meta({ label, values }: { label: string; values: string[] }) {
  return (
    <div>
      <div className="text-xs font-semibold uppercase text-[var(--muted)]">{label}</div>
      <div className="mt-1 break-words text-[#344054]">
        {values.length ? values.join(", ") : "-"}
      </div>
    </div>
  );
}

type EvidenceGroup = {
  id: string;
  items: RuntimeEvidenceLink[];
};

function groupEvidence(evidence: RuntimeEvidenceLink[]): EvidenceGroup[] {
  const groups = new Map<string, RuntimeEvidenceLink[]>();
  for (const item of evidence) {
    const key = evidenceGroupKey(item);
    const group = groups.get(key);
    if (group) {
      group.push(item);
    } else {
      groups.set(key, [item]);
    }
  }
  return Array.from(groups.entries()).map(([id, items]) => ({ id, items }));
}

function evidenceGroupKey(item: RuntimeEvidenceLink) {
  const screenshotPath =
    typeof item.raw.screenshot_path === "string" ? item.raw.screenshot_path : "";
  if (screenshotPath) {
    return `screenshot:${screenshotFamily(screenshotPath)}:${item.source_url ?? ""}`;
  }
  const preview = normalizePreview(item.text_preview ?? "");
  if (preview) {
    return `text:${item.source_url ?? ""}:${preview}`;
  }
  const eventId = typeof item.raw.trace_event_id === "string" ? item.raw.trace_event_id : "";
  return `event:${item.source_url ?? ""}:${eventId || item.evidence_id}`;
}

function screenshotFamily(path: string) {
  const file = path.split(/[\\/]/).pop() ?? path;
  return file
    .replace(/\.(png|jpg|jpeg|webp)$/i, "")
    .replace(/[-_]\d{6,}/g, "")
    .replace(/[-_](before|after|full|page|screenshot)$/i, "")
    .toLowerCase();
}

function normalizePreview(value: string) {
  return value.toLowerCase().replace(/\s+/g, " ").trim().slice(0, 220);
}
