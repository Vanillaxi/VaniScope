"use client";

import { Badge } from "@/components/ui/Badge";
import { formatDateTime } from "@/lib/format";

type ToolAuditViewProps = {
  rows: Record<string, unknown>[];
};

export function ToolAuditView({ rows }: ToolAuditViewProps) {
  const failed = rows.filter((row) => row.status === "failed" || row.error_type).length;
  const approvalRequired = rows.filter((row) => row.decision === "approval_required").length;
  const tools = new Set(rows.map((row) => stringValue(row.tool_name)).filter(Boolean));

  return (
    <div className="rounded-md border border-[var(--line)] bg-white p-5">
      <div className="mb-4 flex flex-wrap gap-2">
        <Badge tone="info">Calls: {rows.length}</Badge>
        <Badge>Tools: {tools.size}</Badge>
        <Badge tone={failed ? "danger" : "success"}>Failed: {failed}</Badge>
        <Badge tone={approvalRequired ? "warning" : "neutral"}>
          Approval required: {approvalRequired}
        </Badge>
      </div>
      <div className="overflow-auto">
        <table className="min-w-full border-separate border-spacing-0 text-left text-sm">
          <thead className="text-xs uppercase text-[var(--muted)]">
            <tr>
              {["Time", "Tool", "Provider", "Decision", "Status", "Duration", "Risk"].map(
                (heading) => (
                  <th key={heading} className="border-b border-[var(--line)] px-3 py-2">
                    {heading}
                  </th>
                ),
              )}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, index) => (
              <tr key={index} className="align-top">
                <td className="border-b border-[var(--line)] px-3 py-2 text-xs text-[var(--muted)]">
                  {formatDateTime(stringValue(row.timestamp), "en", "-")}
                </td>
                <td className="border-b border-[var(--line)] px-3 py-2 font-semibold text-[#344054]">
                  {stringValue(row.tool_name) || "-"}
                </td>
                <td className="border-b border-[var(--line)] px-3 py-2">
                  {stringValue(row.provider_type) || "-"}
                </td>
                <td className="border-b border-[var(--line)] px-3 py-2">
                  {stringValue(row.decision) || "-"}
                </td>
                <td className="border-b border-[var(--line)] px-3 py-2">
                  {stringValue(row.status) || "-"}
                </td>
                <td className="border-b border-[var(--line)] px-3 py-2">
                  {row.duration_ms === undefined ? "-" : `${String(row.duration_ms)}ms`}
                </td>
                <td className="border-b border-[var(--line)] px-3 py-2">
                  {stringValue(row.risk_level) || "-"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function stringValue(value: unknown) {
  return typeof value === "string" ? value : "";
}
