"use client";

import { Badge } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";
import { formatDateTime } from "@/lib/format";
import { screenshotUrl } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import type {
  RuntimeEvidenceLink,
  RuntimeGraphNode,
  RuntimeTimelineItem,
} from "@/lib/types";

type StepDetailPanelProps = {
  taskId: string;
  title?: string;
  node?: RuntimeGraphNode | null;
  item?: RuntimeTimelineItem | null;
  evidence?: RuntimeEvidenceLink[];
};

export function StepDetailPanel({
  taskId,
  title = "Step Detail",
  node,
  item,
  evidence = [],
}: StepDetailPanelProps) {
  const { language, t } = useI18n();
  const detail = normalizeDetail(node, item);
  const relatedEvidence = evidence.filter((entry) =>
    detail.evidenceIds.includes(entry.evidence_id),
  );
  const screenshots = screenshotCandidates(detail.raw, relatedEvidence);

  return (
    <Card className="p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold">{title}</h2>
          <div className="mt-1 text-sm text-[var(--muted)]">
            {detail.label || "Select a node or event"}
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          {detail.type ? <Badge tone="info">{detail.type}</Badge> : null}
          {detail.status ? <Badge tone={statusTone(detail.status)}>{detail.status}</Badge> : null}
        </div>
      </div>

      {detail.empty ? (
        <div className="mt-4 rounded-md border border-dashed border-[var(--line)] p-5 text-sm text-[var(--muted)]">
          Select a Timeline event or Graph node to inspect URLs, readiness, verification,
          screenshots, evidence, and raw payload.
        </div>
      ) : (
        <div className="mt-5 grid gap-5">
          <div className="grid gap-3 text-sm sm:grid-cols-2">
            <Meta label="Started" value={formatDateTime(detail.timestamp, language, "-")} />
            <Meta label="Duration" value={formatDuration(detail.durationMs)} />
            <Meta label="URL before" value={stringFromPath(detail.raw, ["url_before"])} />
            <Meta label="URL after" value={stringFromPath(detail.raw, ["url_after"])} />
            <Meta label="Title before" value={stringFromPath(detail.raw, ["title_before"])} />
            <Meta
              label="Title after"
              value={
                stringFromPath(detail.raw, ["title_after"]) ||
                stringFromPath(detail.raw, ["title"])
              }
            />
          </div>

          <SignalGrid raw={detail.raw} />

          {screenshots.length ? (
            <div>
              <div className="mb-2 text-xs font-semibold uppercase text-[var(--muted)]">
                Screenshots
              </div>
              <div className="grid gap-3 sm:grid-cols-2">
                {screenshots.map((shot) => {
                  const src = screenshotUrl(taskId, shot.path);
                  return src ? (
                    <a
                      key={`${shot.label}-${shot.path}`}
                      href={src}
                      target="_blank"
                      rel="noreferrer"
                      className="block overflow-hidden rounded-md border border-[var(--line)] bg-white"
                    >
                      <div className="border-b border-[var(--line)] px-3 py-2 text-xs font-semibold text-[#344054]">
                        {shot.label}
                      </div>
                      {/* eslint-disable-next-line @next/next/no-img-element */}
                      <img
                        src={src}
                        alt={shot.label}
                        className="aspect-video w-full object-cover"
                      />
                    </a>
                  ) : null;
                })}
              </div>
            </div>
          ) : null}

          <div className="grid gap-3 text-sm sm:grid-cols-2">
            <Meta label="Evidence ids" value={detail.evidenceIds.join(", ")} />
            <Meta
              label={t.inspector.artifactRefs}
              value={detail.artifactRefs.join(", ")}
            />
          </div>

          {relatedEvidence.length ? (
            <div>
              <div className="mb-2 text-xs font-semibold uppercase text-[var(--muted)]">
                Produced Evidence
              </div>
              <div className="grid gap-2">
                {relatedEvidence.map((entry) => (
                  <div
                    key={entry.evidence_id}
                    className="rounded-md border border-[var(--line)] bg-white p-3 text-sm"
                  >
                    <div className="font-semibold text-[var(--brand-dark)]">
                      {entry.evidence_id}
                    </div>
                    <div className="mt-1 break-all text-xs text-[var(--muted)]">
                      {entry.source_url || "-"}
                    </div>
                    {entry.text_preview ? (
                      <div className="mt-2 leading-6 text-[#344054]">{entry.text_preview}</div>
                    ) : null}
                  </div>
                ))}
              </div>
            </div>
          ) : null}

          <div>
            <div className="mb-2 text-xs font-semibold uppercase text-[var(--muted)]">
              {t.inspector.rawPayload}
            </div>
            <pre className="max-h-96 overflow-auto rounded-md bg-[#101828] p-3 text-xs leading-5 text-[#f8fafc]">
              {JSON.stringify(detail.raw ?? {}, null, 2)}
            </pre>
          </div>
        </div>
      )}
    </Card>
  );
}

function SignalGrid({ raw }: { raw: Record<string, unknown> }) {
  const readiness = objectFromPath(raw, ["readiness"]) || objectFromPath(raw, ["payload", "readiness"]);
  const signals =
    objectFromPath(raw, ["signals"]) ||
    objectFromPath(raw, ["payload", "signals"]) ||
    objectFromPath(readiness ?? {}, ["signals"]);
  const verification =
    objectFromPath(raw, ["verification_result"]) ||
    objectFromPath(raw, ["payload", "verification_result"]) ||
    objectFromPath(raw, ["observation", "verification"]);

  if (!signals && !verification) return null;

  return (
    <div className="grid gap-3 lg:grid-cols-2">
      {signals ? (
        <div>
          <div className="mb-2 text-xs font-semibold uppercase text-[var(--muted)]">
            Readiness Signals
          </div>
          <div className="grid gap-2 sm:grid-cols-2">
            {Object.entries(signals).map(([key, value]) => (
              <div
                key={key}
                className="flex items-center justify-between gap-2 rounded-md border border-[var(--line)] bg-white px-3 py-2 text-xs"
              >
                <span className="break-words text-[#344054]">{key}</span>
                <Badge tone={value ? "success" : "warning"}>{String(value)}</Badge>
              </div>
            ))}
          </div>
        </div>
      ) : null}
      {verification ? (
        <div>
          <div className="mb-2 text-xs font-semibold uppercase text-[var(--muted)]">
            Effect Verification
          </div>
          <pre className="max-h-72 overflow-auto rounded-md bg-[#101828] p-3 text-xs leading-5 text-[#f8fafc]">
            {JSON.stringify(verification, null, 2)}
          </pre>
        </div>
      ) : null}
    </div>
  );
}

function Meta({ label, value }: { label: string; value?: string | null }) {
  return (
    <div>
      <div className="text-xs font-semibold uppercase text-[var(--muted)]">{label}</div>
      <div className="mt-1 break-words text-[#344054]">{value || "-"}</div>
    </div>
  );
}

function normalizeDetail(node?: RuntimeGraphNode | null, item?: RuntimeTimelineItem | null) {
  if (node) {
    const raw = normalizeRaw(node.metadata);
    return {
      empty: false,
      label: node.label,
      type: node.type,
      status: node.status,
      timestamp: node.timestamp,
      durationMs: node.duration_ms,
      evidenceIds: evidenceIds(raw, node.metadata),
      artifactRefs: [stringFromPath(node.metadata, ["source"])].filter(Boolean) as string[],
      raw,
    };
  }
  if (item) {
    return {
      empty: false,
      label: item.title,
      type: item.category,
      status: item.status,
      timestamp: item.timestamp,
      durationMs: item.duration_ms,
      evidenceIds: item.evidence_ids ?? [],
      artifactRefs: item.artifact_refs.map((ref) => ref.artifact_name),
      raw: item.raw ?? {},
    };
  }
  return {
    empty: true,
    label: "",
    type: "",
    status: "",
    timestamp: null,
    durationMs: null,
    evidenceIds: [],
    artifactRefs: [],
    raw: {},
  };
}

function normalizeRaw(metadata: Record<string, unknown>) {
  const raw = objectFromPath(metadata, ["raw"]);
  const payload = objectFromPath(metadata, ["payload"]);
  if (raw) return raw;
  if (payload) return { ...metadata, payload };
  return metadata;
}

function screenshotCandidates(
  raw: Record<string, unknown>,
  evidence: RuntimeEvidenceLink[],
) {
  const values = [
    ["before", stringFromPath(raw, ["screenshot_before"])],
    ["after", stringFromPath(raw, ["screenshot_after"])],
    ["screenshot", stringFromPath(raw, ["screenshot_path"])],
    ["payload before", stringFromPath(raw, ["payload", "screenshot_before"])],
    ["payload after", stringFromPath(raw, ["payload", "screenshot_after"])],
  ];
  for (const entry of evidence) {
    const screenshot = stringFromPath(entry.raw, ["screenshot_path"]);
    if (screenshot) values.push([entry.evidence_id, screenshot]);
  }
  const seen = new Set<string>();
  return values
    .filter((item): item is [string, string] => Boolean(item[1]))
    .filter(([, path]) => {
      if (seen.has(path)) return false;
      seen.add(path);
      return true;
    })
    .map(([label, path]) => ({ label, path }));
}

function evidenceIds(...sources: Record<string, unknown>[]) {
  const ids = new Set<string>();
  for (const source of sources) {
    for (const key of ["evidence_id", "screenshot_evidence_id"]) {
      const value = source[key];
      if (typeof value === "string" && value) ids.add(value);
    }
    const list = source.evidence_ids;
    if (Array.isArray(list)) {
      for (const item of list) if (typeof item === "string") ids.add(item);
    }
  }
  return Array.from(ids);
}

function objectFromPath(source: unknown, path: string[]) {
  let current: unknown = source;
  for (const key of path) {
    if (!current || typeof current !== "object" || Array.isArray(current)) return null;
    current = (current as Record<string, unknown>)[key];
  }
  return current && typeof current === "object" && !Array.isArray(current)
    ? (current as Record<string, unknown>)
    : null;
}

function stringFromPath(source: unknown, path: string[]) {
  let current: unknown = source;
  for (const key of path) {
    if (!current || typeof current !== "object" || Array.isArray(current)) return null;
    current = (current as Record<string, unknown>)[key];
  }
  return typeof current === "string" && current ? current : null;
}

function formatDuration(value?: number | null) {
  if (value === null || value === undefined) return "-";
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
  if (["pending", "running", "approval_required", "requires_approval"].includes(value)) {
    return "warning";
  }
  return "neutral";
}
