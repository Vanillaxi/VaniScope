"use client";

import { Badge } from "@/components/ui/Badge";

type ReviewSummaryViewProps = {
  payload: Record<string, unknown>;
};

export function ReviewSummaryView({ payload }: ReviewSummaryViewProps) {
  const issues = arrayValue(payload.issues);
  const claimChecks = arrayValue(payload.claim_checks);
  const unsupported = claimChecks.filter(
    (item) => isRecord(item) && item.supported === false,
  );
  const passed = payload.passed === true;

  return (
    <div className="rounded-md border border-[var(--line)] bg-white p-5">
      <div className="flex flex-wrap items-center gap-2">
        <Badge tone={passed ? "success" : "warning"}>
          {passed ? "Review passed" : "Needs review"}
        </Badge>
        <Badge>Score: {String(payload.score ?? "-")}</Badge>
        <Badge tone={unsupported.length ? "warning" : "neutral"}>
          Unsupported: {unsupported.length}
        </Badge>
      </div>
      {typeof payload.summary === "string" ? (
        <p className="mt-4 text-sm leading-7 text-[#344054]">{payload.summary}</p>
      ) : null}
      <IssueList title="Issues" values={issues} />
      <IssueList title="Unsupported claims" values={unsupported} />
    </div>
  );
}

function IssueList({ title, values }: { title: string; values: unknown[] }) {
  if (!values.length) return null;
  return (
    <div className="mt-5">
      <div className="mb-2 text-sm font-semibold text-[#344054]">{title}</div>
      <div className="grid gap-2">
        {values.map((value, index) => (
          <div key={index} className="rounded-md border border-[var(--line)] bg-[var(--panel-soft)] p-3 text-sm leading-6 text-[#344054]">
            {isRecord(value)
              ? String(value.message ?? value.claim ?? value.reason ?? JSON.stringify(value))
              : String(value)}
          </div>
        ))}
      </div>
    </div>
  );
}

function arrayValue(value: unknown) {
  return Array.isArray(value) ? value : [];
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
