"use client";

import { Badge } from "@/components/ui/Badge";

type LlmSummaryViewProps = {
  rows: Record<string, unknown>[];
};

export function LlmSummaryView({ rows }: LlmSummaryViewProps) {
  const providers = unique(rows.map((row) => stringValue(row.provider)));
  const models = unique(rows.map((row) => stringValue(row.model)));
  const modes = unique(rows.map((row) => stringValue(row.mode)));
  const tokenTotal = rows.reduce(
    (sum, row) =>
      sum + numberValue(row.prompt_tokens_estimated) + numberValue(row.completion_tokens_estimated),
    0,
  );
  const realCalls = rows.filter((row) =>
    ["real", "real_llm", "openai_compatible"].includes(stringValue(row.mode)),
  ).length;

  return (
    <div className="rounded-md border border-[var(--line)] bg-white p-5">
      <div className="flex flex-wrap gap-2">
        <Badge tone={realCalls ? "warning" : "success"}>
          {realCalls ? "Real LLM used" : "No real LLM calls"}
        </Badge>
        <Badge>Calls: {rows.length}</Badge>
        <Badge>Tokens est.: {tokenTotal}</Badge>
      </div>
      <div className="mt-4 grid gap-3 text-sm sm:grid-cols-2 lg:grid-cols-4">
        <Meta label="Mode" value={modes.join(", ") || "deterministic"} />
        <Meta label="Provider" value={providers.join(", ") || "none"} />
        <Meta label="Model" value={models.join(", ") || "-"} />
        <Meta label="Real calls" value={String(realCalls)} />
      </div>
      {!rows.length ? (
        <p className="mt-4 rounded-md bg-[var(--panel-soft)] p-3 text-sm text-[#344054]">
          No real LLM calls were made. This task used deterministic / fake planner mode.
        </p>
      ) : null}
    </div>
  );
}

function Meta({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-xs font-semibold uppercase text-[var(--muted)]">{label}</div>
      <div className="mt-1 break-words text-[#344054]">{value || "-"}</div>
    </div>
  );
}

function unique(values: string[]) {
  return Array.from(new Set(values.filter(Boolean)));
}

function stringValue(value: unknown) {
  return typeof value === "string" ? value : "";
}

function numberValue(value: unknown) {
  return typeof value === "number" ? value : 0;
}
