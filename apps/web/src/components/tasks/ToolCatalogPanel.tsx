"use client";

import { useEffect, useState } from "react";
import { Badge } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";
import { getToolCatalog } from "@/lib/api";
import type { ToolCatalogItem } from "@/lib/types";

export function ToolCatalogPanel() {
  const [tools, setTools] = useState<ToolCatalogItem[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    getToolCatalog()
      .then((payload) => {
        if (cancelled) return;
        setTools(
          payload.tools.filter((tool) => tool.tags.includes("v2") && !tool.compatibility_wrapper),
        );
        setError(null);
      })
      .catch((reason: unknown) => {
        if (!cancelled) setError(reason instanceof Error ? reason.message : String(reason));
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <Card className="p-5">
      <div className="mb-4">
        <h2 className="text-lg font-semibold">Browser Tool Contract v2</h2>
        <p className="mt-1 text-sm text-[var(--muted)]">
          ToolGateway metadata used by prompts, safety checks, and inspector display.
        </p>
      </div>
      {error ? (
        <div className="rounded-md border border-[#fecdca] bg-[#fef3f2] p-3 text-sm text-[var(--danger)]">
          {error}
        </div>
      ) : (
        <div className="overflow-x-auto rounded-md border border-[var(--line)]">
          <table className="min-w-full border-collapse text-sm">
            <thead className="bg-[var(--panel-soft)] text-left text-xs uppercase text-[var(--muted)]">
              <tr>
                <th className="px-3 py-2">Tool</th>
                <th className="px-3 py-2">Risk</th>
                <th className="px-3 py-2">Public</th>
                <th className="px-3 py-2">Evidence</th>
                <th className="px-3 py-2">Screenshot</th>
                <th className="px-3 py-2">Session</th>
                <th className="px-3 py-2">Status</th>
              </tr>
            </thead>
            <tbody>
              {tools.map((tool) => (
                <tr key={tool.tool_id} className="border-t border-[var(--line)] bg-white">
                  <td className="max-w-80 px-3 py-3">
                    <div className="font-semibold text-[#26323f]">{tool.tool_id}</div>
                    <div className="mt-1 text-xs leading-5 text-[var(--muted)]">
                      {tool.description}
                    </div>
                  </td>
                  <td className="px-3 py-3">
                    <Badge tone={tool.risk_level === "read_only" ? "success" : "warning"}>
                      {tool.risk_level}
                    </Badge>
                  </td>
                  <td className="px-3 py-3">{yesNo(tool.public_web_allowed)}</td>
                  <td className="px-3 py-3">{yesNo(tool.produces_evidence)}</td>
                  <td className="px-3 py-3">{yesNo(tool.produces_screenshot)}</td>
                  <td className="px-3 py-3">{yesNo(tool.requires_session)}</td>
                  <td className="px-3 py-3">
                    <Badge tone={tool.enabled ? "info" : "danger"}>
                      {tool.enabled ? "enabled" : "disabled"}
                    </Badge>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );
}

function yesNo(value: boolean) {
  return value ? "yes" : "no";
}
