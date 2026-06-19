"use client";

import { EvidenceCards } from "@/components/tasks/artifacts/EvidenceCards";
import { LlmSummaryView } from "@/components/tasks/artifacts/LlmSummaryView";
import { PromptDebugView } from "@/components/tasks/artifacts/PromptDebugView";
import { RawArtifactView } from "@/components/tasks/artifacts/RawArtifactView";
import { ReportView } from "@/components/tasks/artifacts/ReportView";
import { ReviewSummaryView } from "@/components/tasks/artifacts/ReviewSummaryView";
import { ToolAuditView } from "@/components/tasks/artifacts/ToolAuditView";
import { TraceDebugView } from "@/components/tasks/artifacts/TraceDebugView";
import { Badge } from "@/components/ui/Badge";
import { rendererKindForArtifact } from "@/lib/artifactRenderers";
import { formatArtifactContent } from "@/lib/format";

type ArtifactRendererProps = {
  taskId: string;
  artifactName: string;
  content: string;
  developerView?: boolean;
  compact?: boolean;
};

export function ArtifactRenderer({
  taskId,
  artifactName,
  content,
  developerView = false,
  compact = false,
}: ArtifactRendererProps) {
  const formatted = formatForRaw(artifactName, content, compact);
  const rows = parseJsonl(content);
  const payload = parseJson(content);
  const kind = rendererKindForArtifact(artifactName);

  if (developerView || kind === "raw") {
    return (
      <RawArtifactView
        taskId={taskId}
        artifactName={artifactName}
        content={formatted}
        defaultOpen
      />
    );
  }

  return (
    <div className="space-y-4">
      {kind === "report" ? <ReportView content={content} /> : null}
      {kind === "evidence" ? <EvidenceCards rows={rows} /> : null}
      {kind === "review" ? <ReviewSummaryView payload={payload} /> : null}
      {kind === "toolAudit" ? <ToolAuditView rows={rows} /> : null}
      {kind === "llmCalls" ? <LlmSummaryView rows={rows} /> : null}
      {kind === "prompt" ? <PromptDebugView artifactName={artifactName} /> : null}
      {kind === "trace" || kind === "transcript" || kind === "timeline" ? (
        <TraceDebugView rows={rows.length ? rows : arrayPayload(payload)} label={artifactName} />
      ) : null}
      {kind === "approval" || kind === "recovery" || kind === "skillResult" ? (
        <SummaryPayloadView artifactName={artifactName} rows={rows} payload={payload} />
      ) : null}
      <RawArtifactView
        taskId={taskId}
        artifactName={artifactName}
        content={formatted}
        title="Developer raw"
      />
    </div>
  );
}

function SummaryPayloadView({
  artifactName,
  rows,
  payload,
}: {
  artifactName: string;
  rows: Record<string, unknown>[];
  payload: Record<string, unknown>;
}) {
  const count = rows.length || (Object.keys(payload).length ? 1 : 0);
  return (
    <div className="rounded-md border border-[var(--line)] bg-white p-5">
      <div className="flex flex-wrap gap-2">
        <Badge tone="info">{artifactName}</Badge>
        <Badge>Records: {count}</Badge>
      </div>
      {rows.slice(0, 5).map((row, index) => (
        <div key={index} className="mt-3 rounded-md bg-[var(--panel-soft)] p-3 text-sm leading-6 text-[#344054]">
          {String(row.summary ?? row.status ?? row.kind ?? row.approval_id ?? JSON.stringify(row))}
        </div>
      ))}
      {!rows.length && Object.keys(payload).length ? (
        <div className="mt-3 rounded-md bg-[var(--panel-soft)] p-3 text-sm leading-6 text-[#344054]">
          {String(payload.summary ?? payload.status ?? payload.skill_id ?? JSON.stringify(payload))}
        </div>
      ) : null}
    </div>
  );
}

function parseJson(content: string): Record<string, unknown> {
  try {
    const value = JSON.parse(content) as unknown;
    return isRecord(value) ? value : {};
  } catch {
    return {};
  }
}

function parseJsonl(content: string): Record<string, unknown>[] {
  return content
    .split("\n")
    .filter((line) => line.trim())
    .flatMap((line) => {
      try {
        const value = JSON.parse(line) as unknown;
        return isRecord(value) ? [value] : [];
      } catch {
        return [];
      }
    });
}

function arrayPayload(payload: Record<string, unknown>) {
  const items = payload.items ?? payload.timeline_items ?? payload.events;
  return Array.isArray(items) ? items.filter(isRecord) : [];
}

function formatForRaw(artifactName: string, content: string, compact: boolean) {
  const maxChars = compact ? 12_000 : 120_000;
  let formatted = content;
  try {
    formatted = formatArtifactContent(artifactName, content);
  } catch {
    formatted = content;
  }
  if (formatted.length <= maxChars) return formatted;
  return `${formatted.slice(0, maxChars)}\n\n...[truncated: ${formatted.length} characters]`;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
