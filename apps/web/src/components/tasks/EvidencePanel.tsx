"use client";

import { Card } from "@/components/ui/Card";
import { useI18n } from "@/lib/i18n";
import type { RuntimeEvidenceLink } from "@/lib/types";

type EvidencePanelProps = {
  evidence: RuntimeEvidenceLink[];
};

export function EvidencePanel({ evidence }: EvidencePanelProps) {
  const { t } = useI18n();

  return (
    <Card className="p-5">
      <div className="mb-4">
        <h2 className="text-lg font-semibold">{t.inspector.evidence}</h2>
        <p className="mt-1 text-sm text-[var(--muted)]">
          {evidence.length} {t.inspector.evidenceLinked}
        </p>
      </div>
      {evidence.length ? (
        <div className="grid gap-3">
          {evidence.map((item) => (
            <div
              key={item.evidence_id}
              className="rounded-md border border-[var(--line)] bg-white p-4"
            >
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-semibold text-[var(--brand-dark)]">
                  {item.evidence_id}
                </span>
                {item.page_title ? (
                  <span className="text-sm text-[var(--muted)]">{item.page_title}</span>
                ) : null}
              </div>
              {item.source_url ? (
                <div className="mt-2 break-all text-xs text-[var(--muted)]">
                  {item.source_url}
                </div>
              ) : null}
              {item.text_preview ? (
                <div className="mt-3 rounded-md bg-[var(--panel-soft)] p-3 text-sm leading-6 text-[#344054]">
                  {item.text_preview}
                </div>
              ) : null}
              <div className="mt-3 grid gap-3 text-sm sm:grid-cols-2">
                <Meta label={t.inspector.reportSections} values={item.report_sections} />
                <Meta label={t.inspector.reviewIssues} values={item.review_issue_ids} />
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="rounded-md border border-dashed border-[var(--line)] p-5 text-sm text-[var(--muted)]">
          {t.inspector.noEvidence}
        </div>
      )}
    </Card>
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
