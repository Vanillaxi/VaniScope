"use client";

import { ArtifactViewer } from "@/components/tasks/ArtifactViewer";
import { Badge } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";
import { useI18n } from "@/lib/i18n";

type ReviewPanelProps = {
  taskId: string;
  artifacts: string[];
  reviewSummary?: Record<string, unknown>;
};

export function ReviewPanel({ taskId, artifacts, reviewSummary = {} }: ReviewPanelProps) {
  const { t } = useI18n();
  const available = reviewSummary.available === true;
  const issues = arrayValue(reviewSummary.issues);
  const unsupportedClaims = arrayValue(reviewSummary.unsupported_claims);

  if (!available && !artifacts.includes("review.json")) {
    return (
      <Card className="p-5">
        <h2 className="text-lg font-semibold">{t.inspector.review}</h2>
        <div className="mt-4 rounded-md border border-dashed border-[var(--line)] p-5 text-sm text-[var(--muted)]">
          {t.inspector.reviewUnavailable}
        </div>
      </Card>
    );
  }

  return (
    <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_360px]">
      <div className="flex flex-col gap-5">
        <ArtifactViewer taskId={taskId} artifactName="review.json" title={t.inspector.review} />
        {artifacts.includes("revision_plan.json") ? (
          <ArtifactViewer
            taskId={taskId}
            artifactName="revision_plan.json"
            title="Revision plan"
            compact
          />
        ) : null}
        {artifacts.includes("revised_report.md") ? (
          <ArtifactViewer
            taskId={taskId}
            artifactName="revised_report.md"
            title="Revised report"
            compact
          />
        ) : null}
      </div>
      <Card className="p-5">
        <h2 className="text-lg font-semibold">{t.inspector.summary}</h2>
        <div className="mt-4 grid gap-3 text-sm">
          <Meta label={t.inspector.status} value={String(reviewSummary.status ?? "-")} />
          <Meta label="Score" value={String(reviewSummary.score ?? "-")} />
          <Meta label={t.inspector.issueCount} value={String(reviewSummary.issue_count ?? 0)} />
          <Meta
            label={t.inspector.unsupportedClaims}
            value={String(reviewSummary.unsupported_claim_count ?? 0)}
          />
        </div>
        <IssueList title={t.inspector.issueCount} values={issues} />
        <IssueList title={t.inspector.unsupportedClaims} values={unsupportedClaims} />
      </Card>
    </div>
  );
}

function Meta({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-xs font-semibold uppercase text-[var(--muted)]">{label}</div>
      <div className="mt-1 break-words text-[#344054]">{value}</div>
    </div>
  );
}

function IssueList({ title, values }: { title: string; values: unknown[] }) {
  if (!values.length) return null;
  return (
    <div className="mt-5">
      <div className="mb-2 flex items-center gap-2">
        <Badge tone="warning">{title}</Badge>
      </div>
      <pre className="max-h-72 overflow-auto rounded-md bg-[#101828] p-3 text-xs leading-5 text-[#f8fafc]">
        {JSON.stringify(values, null, 2)}
      </pre>
    </div>
  );
}

function arrayValue(value: unknown) {
  return Array.isArray(value) ? value : [];
}
